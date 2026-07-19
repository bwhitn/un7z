//! Bounded adapters for Python writers, callbacks, and volume providers.

use std::io::{self, Cursor, Read, Seek, SeekFrom, Write};

use pyo3::{
    exceptions::{PyMemoryError, PyTypeError, PyValueError},
    prelude::*,
    types::{PyBool, PyBytes},
};
use un7z::{
    CancellationToken, Error, LimitKind, Result as CoreResult, Volume, VolumeProvider,
    VolumeRequest,
};

use crate::errors::{PythonCallbackError, callback_cancelled_error};

#[derive(Clone, Copy)]
pub(crate) enum SinkMode {
    Writer,
    Callback,
}

pub(crate) struct PythonSink {
    target: Py<PyAny>,
    mode: SinkMode,
    cancellation: CancellationToken,
}

impl PythonSink {
    pub(crate) const fn new(
        target: Py<PyAny>,
        mode: SinkMode,
        cancellation: CancellationToken,
    ) -> Self {
        Self {
            target,
            mode,
            cancellation,
        }
    }

    fn callback_error(error: PyErr) -> io::Error {
        io::Error::other(PythonCallbackError::new(error))
    }
}

impl Write for PythonSink {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        Python::attach(|py| {
            let chunk = PyBytes::new_with(py, bytes.len(), |output| {
                output.copy_from_slice(bytes);
                Ok(())
            })?;
            let target = self.target.bind(py);
            let result = match self.mode {
                SinkMode::Writer => target.call_method1("write", (chunk,)),
                SinkMode::Callback => target.call1((chunk,)),
            }?;
            match self.mode {
                SinkMode::Writer => {
                    let count = result.extract::<usize>().map_err(|_| {
                        PyTypeError::new_err("writer.write() must return an integer byte count")
                    })?;
                    if count > bytes.len() {
                        return Err(PyValueError::new_err(
                            "writer.write() returned more bytes than it received",
                        ));
                    }
                    Ok(count)
                }
                SinkMode::Callback => {
                    if result.is_none() {
                        return Ok(bytes.len());
                    }
                    let is_bool = result.is_instance_of::<PyBool>();
                    if !is_bool {
                        return Err(PyTypeError::new_err(
                            "stream callback must return None or bool",
                        ));
                    }
                    if !result.extract::<bool>()? {
                        self.cancellation.cancel();
                        return Err(callback_cancelled_error(py));
                    }
                    Ok(bytes.len())
                }
            }
        })
        .map_err(Self::callback_error)
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

struct OwnedVolume {
    cursor: Cursor<Vec<u8>>,
}

impl Read for OwnedVolume {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        self.cursor.read(bytes)
    }
}

impl Seek for OwnedVolume {
    fn seek(&mut self, position: SeekFrom) -> io::Result<u64> {
        self.cursor.seek(position)
    }
}

impl Volume for OwnedVolume {
    fn len(&mut self) -> io::Result<u64> {
        u64::try_from(self.cursor.get_ref().len()).map_err(|_| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "Python volume length is not representable as u64",
            )
        })
    }
}

enum ProviderOutcome {
    Missing,
    Bytes(Vec<u8>),
    Limit { requested: u64, maximum: u64 },
}

pub(crate) struct PythonVolumeProvider {
    provider: Py<PyAny>,
    max_total_input_bytes: u64,
}

impl PythonVolumeProvider {
    pub(crate) const fn new(provider: Py<PyAny>, max_total_input_bytes: u64) -> Self {
        Self {
            provider,
            max_total_input_bytes,
        }
    }

    fn invoke(&self, request: &VolumeRequest) -> PyResult<ProviderOutcome> {
        Python::attach(|py| {
            let provider = self.provider.bind(py);
            let response = if provider.hasattr("open_volume")? {
                provider.call_method1("open_volume", (request.index(), request.expected_name()))?
            } else {
                provider.call1((request.index(), request.expected_name()))?
            };
            if response.is_none() {
                return Ok(ProviderOutcome::Missing);
            }
            let bytes = response
                .cast::<PyBytes>()
                .map_err(|_| PyTypeError::new_err("volume provider must return bytes or None"))?;
            let source = bytes.as_bytes();
            let requested = u64::try_from(source.len()).map_err(|_| {
                PyValueError::new_err("Python volume length is not representable as u64")
            })?;
            if requested > self.max_total_input_bytes {
                return Ok(ProviderOutcome::Limit {
                    requested,
                    maximum: self.max_total_input_bytes,
                });
            }
            let mut owned = Vec::new();
            owned
                .try_reserve_exact(source.len())
                .map_err(|_| PyMemoryError::new_err("unable to allocate Python volume copy"))?;
            owned.extend_from_slice(source);
            Ok(ProviderOutcome::Bytes(owned))
        })
    }
}

impl VolumeProvider for PythonVolumeProvider {
    fn open_volume(&mut self, request: &VolumeRequest) -> CoreResult<Box<dyn Volume>> {
        match self.invoke(request) {
            Ok(ProviderOutcome::Missing) => Err(Error::MissingVolume {
                expected: request.expected_name().to_owned(),
            }),
            Ok(ProviderOutcome::Limit { requested, maximum }) => Err(Error::LimitExceeded {
                limit: LimitKind::TotalInputBytes,
                requested,
                maximum,
            }),
            Ok(ProviderOutcome::Bytes(bytes)) => Ok(Box::new(OwnedVolume {
                cursor: Cursor::new(bytes),
            })),
            Err(error) => Err(Error::Io(io::Error::other(PythonCallbackError::new(error)))),
        }
    }
}
