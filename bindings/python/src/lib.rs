#![forbid(unsafe_code)]
#![deny(
    clippy::expect_used,
    clippy::indexing_slicing,
    clippy::panic,
    clippy::unwrap_used
)]
//! Native implementation of the `un7z` Python package.

use pyo3::prelude::*;

mod archive;
mod callback;
mod config;
mod errors;
mod metadata;

/// Native implementation module installed as `un7z._native`.
#[pymodule]
#[pyo3(name = "_native")]
fn native_module(module: &Bound<'_, PyModule>) -> PyResult<()> {
    errors::guard(|| {
        errors::add_exceptions(module)?;
        module.add_class::<archive::PyArchive>()?;
        module.add_class::<config::PyLimits>()?;
        module.add_class::<config::PyCancellationToken>()?;
        module.add_class::<metadata::PyEntry>()?;
        module.add_class::<metadata::PyArchiveResources>()?;
        module.add_function(wrap_pyfunction!(archive::open_bytes, module)?)?;
        module.add_function(wrap_pyfunction!(archive::open_path, module)?)?;
        module.add_function(wrap_pyfunction!(archive::open_volumes, module)?)?;
        module.add("DEFAULT_MAX_WORK_UNITS", config::DEFAULT_WORK_UNITS)?;
        module.add("IMPLEMENTATION_STATUS", "phase-7-python-binding-pre-alpha")?;
        Ok(())
    })
}
