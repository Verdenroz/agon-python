//! AGON Core: Rust implementation of AGON encoding formats
//!
//! All format classes inherit from AGONFormat base class:
//! - AGONRows: Row-based tabular encoding
//! - AGONColumns: Columnar encoding with type clustering
//! - AGONStruct: Template-based encoding for nested patterns

use pyo3::exceptions::PyNotImplementedError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;

mod error;
mod formats;
mod types;
mod utils;

pub use error::AgonError;
pub use formats::{columns, rows, struct_fmt};
pub use types::JsonValue;

// ============================================================================
// AGONFormat - Abstract base class
// ============================================================================

/// Abstract base class for AGON format codecs.
///
/// All AGON formats inherit from this class and implement:
///   - encode(data, include_header=False) -> str
///   - decode(payload) -> object
///   - hint() -> str
///
/// Provides concrete method:
///   - project_data(data, keep_paths) -> projected data
#[pyclass(subclass)]
struct AGONFormat;

#[pymethods]
impl AGONFormat {
    #[new]
    fn new() -> Self {
        AGONFormat
    }

    /// Encode data to this format. Must be implemented by subclasses.
    #[staticmethod]
    #[pyo3(signature = (_data, _include_header = false))]
    fn encode(_data: &Bound<'_, PyAny>, _include_header: bool) -> PyResult<String> {
        Err(PyNotImplementedError::new_err(
            "encode() must be implemented by subclass",
        ))
    }

    /// Decode a payload in this format. Must be implemented by subclasses.
    #[staticmethod]
    fn decode(_payload: &str) -> PyResult<Py<PyAny>> {
        Err(PyNotImplementedError::new_err(
            "decode() must be implemented by subclass",
        ))
    }

    /// Return a short hint describing this format. Must be implemented by subclasses.
    #[staticmethod]
    fn hint() -> PyResult<String> {
        Err(PyNotImplementedError::new_err(
            "hint() must be implemented by subclass",
        ))
    }

    /// Project data to only keep specified fields.
    ///
    /// Args:
    ///     data: List of objects to project
    ///     keep_paths: List of field paths to keep (supports dotted paths like "user.name")
    ///
    /// Returns:
    ///     Projected data with only the specified fields
    #[staticmethod]
    fn project_data(
        py: Python<'_>,
        data: &Bound<'_, PyList>,
        keep_paths: Vec<String>,
    ) -> PyResult<Py<PyList>> {
        let keep_tree = build_keep_tree(&keep_paths);
        let result = PyList::empty(py);

        for item in data.iter() {
            if item.is_instance_of::<PyDict>() {
                let dict = item
                    .cast::<PyDict>()
                    .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
                let projected = project_obj(py, dict, &keep_tree)?;
                result.append(projected)?;
            }
        }

        Ok(result.unbind())
    }

    fn __repr__(&self) -> String {
        "AGONFormat()".to_string()
    }
}

/// Recursive keep tree: None means "keep whole value", Some(map) means "keep these subfields"
#[derive(Default)]
struct KeepTree {
    children: HashMap<String, Option<Box<KeepTree>>>,
}

// Helper: Build keep tree from dotted paths
fn build_keep_tree(keep_paths: &[String]) -> KeepTree {
    let mut tree = KeepTree::default();

    for raw_path in keep_paths {
        let path = raw_path.trim().trim_matches('.');
        if path.is_empty() {
            continue;
        }
        let parts: Vec<&str> = path.split('.').filter(|p| !p.is_empty()).collect();
        if parts.is_empty() {
            continue;
        }

        // Walk the path and build nested structure
        let mut cur = &mut tree;
        for (i, part) in parts.iter().enumerate() {
            let is_last = i == parts.len() - 1;
            let key = part.to_string();

            if is_last {
                // Leaf: set to None if not already a subtree
                cur.children.entry(key).or_insert(None);
            } else {
                // Intermediate: ensure subtree exists
                let entry = cur
                    .children
                    .entry(key)
                    .or_insert_with(|| Some(Box::new(KeepTree::default())));
                if let Some(subtree) = entry {
                    cur = subtree.as_mut();
                } else {
                    // Was None (keep whole), upgrade to subtree
                    let new_subtree = Box::new(KeepTree::default());
                    *entry = Some(new_subtree);
                    cur = entry.as_mut().unwrap().as_mut();
                }
            }
        }
    }

    tree
}

// Helper: Project a single object recursively
fn project_obj(
    py: Python<'_>,
    obj: &Bound<'_, PyDict>,
    keep_tree: &KeepTree,
) -> PyResult<Py<PyDict>> {
    let out = PyDict::new(py);

    for (key, sub_keep) in &keep_tree.children {
        if let Ok(Some(value)) = obj.get_item(key) {
            match sub_keep {
                None => {
                    // Leaf: keep the whole value
                    out.set_item(key, &value)?;
                }
                Some(sub_tree) => {
                    // Need to project nested structure
                    if value.is_none() {
                        out.set_item(key, &value)?;
                    } else if value.is_instance_of::<PyDict>() {
                        let nested_dict = value
                            .cast::<PyDict>()
                            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
                        let projected = project_obj(py, nested_dict, sub_tree)?;
                        out.set_item(key, projected)?;
                    } else if value.is_instance_of::<PyList>() {
                        let nested_list = value
                            .cast::<PyList>()
                            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

                        // Check if list is empty or all items are dicts
                        let all_dicts = nested_list
                            .iter()
                            .all(|item| item.is_instance_of::<PyDict>());

                        if nested_list.is_empty() || all_dicts {
                            let projected_list = PyList::empty(py);
                            for item in nested_list.iter() {
                                let item_dict = item.cast::<PyDict>().map_err(|e| {
                                    pyo3::exceptions::PyValueError::new_err(e.to_string())
                                })?;
                                let projected = project_obj(py, item_dict, sub_tree)?;
                                projected_list.append(projected)?;
                            }
                            out.set_item(key, projected_list)?;
                        } else {
                            // Mixed list or not all dicts: keep as-is
                            out.set_item(key, &value)?;
                        }
                    } else {
                        // Not a dict or list: keep as-is
                        out.set_item(key, &value)?;
                    }
                }
            }
        }
    }

    Ok(out.unbind())
}

// ============================================================================
// AGONRows - Row-based tabular encoding
// ============================================================================

/// Row-based tabular encoding format.
#[pyclass(extends=AGONFormat)]
struct AGONRows;

#[pymethods]
impl AGONRows {
    #[new]
    fn new() -> (Self, AGONFormat) {
        (AGONRows, AGONFormat)
    }

    #[staticmethod]
    #[pyo3(signature = (data, include_header = false))]
    fn encode(data: &Bound<'_, PyAny>, include_header: bool) -> PyResult<String> {
        let value = types::py_to_json(data)?;
        rows::encode(&value, include_header).map_err(|e| e.into())
    }

    #[staticmethod]
    fn decode(py: Python<'_>, payload: &str) -> PyResult<Py<PyAny>> {
        let value = rows::decode(payload)?;
        types::json_to_py(py, &value)
    }

    #[staticmethod]
    fn hint() -> String {
        "Return in AGON rows format: Start with @AGON rows header, encode arrays as name[N]{fields} with tab-delimited rows".to_string()
    }

    fn __repr__(&self) -> String {
        "AGONRows()".to_string()
    }
}

// ============================================================================
// AGONColumns - Columnar encoding
// ============================================================================

/// Columnar encoding that transposes arrays to group by field.
#[pyclass(extends=AGONFormat)]
struct AGONColumns;

#[pymethods]
impl AGONColumns {
    #[new]
    fn new() -> (Self, AGONFormat) {
        (AGONColumns, AGONFormat)
    }

    #[staticmethod]
    #[pyo3(signature = (data, include_header = false))]
    fn encode(data: &Bound<'_, PyAny>, include_header: bool) -> PyResult<String> {
        let value = types::py_to_json(data)?;
        columns::encode(&value, include_header).map_err(|e| e.into())
    }

    #[staticmethod]
    fn decode(py: Python<'_>, payload: &str) -> PyResult<Py<PyAny>> {
        let value = columns::decode(payload)?;
        types::json_to_py(py, &value)
    }

    #[staticmethod]
    fn hint() -> String {
        "Return in AGON columns format: Start with @AGON columns header, transpose arrays to name[N] with ├/└ field: val1, val2, ...".to_string()
    }

    fn __repr__(&self) -> String {
        "AGONColumns()".to_string()
    }
}

// ============================================================================
// AGONStruct - Template-based encoding
// ============================================================================

/// Template-based encoding that detects repeated object patterns.
#[pyclass(extends=AGONFormat)]
struct AGONStruct;

#[pymethods]
impl AGONStruct {
    #[new]
    fn new() -> (Self, AGONFormat) {
        (AGONStruct, AGONFormat)
    }

    #[staticmethod]
    #[pyo3(signature = (data, include_header = false))]
    fn encode(data: &Bound<'_, PyAny>, include_header: bool) -> PyResult<String> {
        let value = types::py_to_json(data)?;
        struct_fmt::encode(&value, include_header).map_err(|e| e.into())
    }

    #[staticmethod]
    fn decode(py: Python<'_>, payload: &str) -> PyResult<Py<PyAny>> {
        let value = struct_fmt::decode(payload)?;
        types::json_to_py(py, &value)
    }

    #[staticmethod]
    fn hint() -> String {
        "Return in AGON struct format: Start with @AGON struct header, define templates as @Struct: fields, instantiate as Struct(v1, v2)".to_string()
    }

    fn __repr__(&self) -> String {
        "AGONStruct()".to_string()
    }
}

// ============================================================================
// EncodingResult
// ============================================================================

/// Result of parallel encoding with format selection.
#[pyclass]
#[derive(Clone)]
struct EncodingResult {
    #[pyo3(get)]
    format: String,
    #[pyo3(get)]
    text: String,
    #[pyo3(get)]
    header: String,
    #[pyo3(get)]
    token_estimate: usize,
}

#[pymethods]
impl EncodingResult {
    fn __repr__(&self) -> String {
        format!(
            "EncodingResult(format={:?}, len={}, tokens={})",
            self.format,
            self.text.len(),
            self.token_estimate
        )
    }
}

// ============================================================================
// Module-level functions
// ============================================================================

#[pyfunction]
#[pyo3(signature = (data, force = false, min_savings = 0.10, encoding = None))]
fn encode_auto_parallel(
    data: &Bound<'_, PyAny>,
    force: bool,
    min_savings: f64,
    encoding: Option<&str>,
) -> PyResult<EncodingResult> {
    let value = types::py_to_json(data)?;
    let result = formats::encode_auto_parallel(&value, force, min_savings, encoding)?;
    Ok(EncodingResult {
        format: result.format,
        text: result.text,
        header: result.header,
        token_estimate: result.token_estimate,
    })
}

/// Count tokens using tiktoken encoding
#[pyfunction]
#[pyo3(signature = (text, encoding = "o200k_base"))]
fn count_tokens(text: &str, encoding: &str) -> PyResult<usize> {
    utils::count_tokens(text, encoding)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn encode_all_parallel(data: &Bound<'_, PyAny>) -> PyResult<Vec<EncodingResult>> {
    let value = types::py_to_json(data)?;
    let results = formats::encode_all_parallel(&value)?;
    Ok(results
        .into_iter()
        .map(|r| EncodingResult {
            format: r.format,
            text: r.text,
            header: r.header,
            token_estimate: r.token_estimate,
        })
        .collect())
}

// ============================================================================
// Python module
// ============================================================================

#[pymodule]
fn agon_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<AGONFormat>()?;
    m.add_class::<AGONRows>()?;
    m.add_class::<AGONColumns>()?;
    m.add_class::<AGONStruct>()?;
    m.add_class::<EncodingResult>()?;
    m.add_function(wrap_pyfunction!(encode_auto_parallel, m)?)?;
    m.add_function(wrap_pyfunction!(encode_all_parallel, m)?)?;
    m.add_function(wrap_pyfunction!(count_tokens, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    // ========================================================================
    // build_keep_tree tests (pure Rust)
    // ========================================================================

    #[test]
    fn test_build_keep_tree_single_field() {
        let paths = vec!["name".to_string()];
        let tree = build_keep_tree(&paths);
        assert!(tree.children.contains_key("name"));
        assert!(tree.children.get("name").unwrap().is_none()); // Leaf node
    }

    #[test]
    fn test_build_keep_tree_multiple_fields() {
        let paths = vec!["name".to_string(), "age".to_string(), "email".to_string()];
        let tree = build_keep_tree(&paths);
        assert_eq!(tree.children.len(), 3);
        assert!(tree.children.contains_key("name"));
        assert!(tree.children.contains_key("age"));
        assert!(tree.children.contains_key("email"));
    }

    #[test]
    fn test_build_keep_tree_nested_path() {
        let paths = vec!["user.name".to_string()];
        let tree = build_keep_tree(&paths);
        assert!(tree.children.contains_key("user"));
        let user_subtree = tree.children.get("user").unwrap();
        assert!(user_subtree.is_some());
        let user = user_subtree.as_ref().unwrap();
        assert!(user.children.contains_key("name"));
    }

    #[test]
    fn test_build_keep_tree_deeply_nested() {
        let paths = vec!["a.b.c.d".to_string()];
        let tree = build_keep_tree(&paths);

        let a = tree.children.get("a").unwrap().as_ref().unwrap();
        let b = a.children.get("b").unwrap().as_ref().unwrap();
        let c = b.children.get("c").unwrap().as_ref().unwrap();
        assert!(c.children.contains_key("d"));
        assert!(c.children.get("d").unwrap().is_none()); // Leaf
    }

    #[test]
    fn test_build_keep_tree_mixed_depth() {
        let paths = vec![
            "id".to_string(),
            "user.name".to_string(),
            "user.email".to_string(),
        ];
        let tree = build_keep_tree(&paths);

        // Top-level "id"
        assert!(tree.children.contains_key("id"));
        assert!(tree.children.get("id").unwrap().is_none());

        // Nested "user.name" and "user.email"
        let user = tree.children.get("user").unwrap().as_ref().unwrap();
        assert!(user.children.contains_key("name"));
        assert!(user.children.contains_key("email"));
    }

    #[test]
    fn test_build_keep_tree_empty_paths() {
        let paths: Vec<String> = vec![];
        let tree = build_keep_tree(&paths);
        assert!(tree.children.is_empty());
    }

    #[test]
    fn test_build_keep_tree_whitespace_paths() {
        let paths = vec!["  ".to_string(), "".to_string(), "...".to_string()];
        let tree = build_keep_tree(&paths);
        assert!(tree.children.is_empty());
    }

    #[test]
    fn test_build_keep_tree_leading_trailing_dots() {
        let paths = vec![".name.".to_string()];
        let tree = build_keep_tree(&paths);
        assert!(tree.children.contains_key("name"));
    }

    // Note: PyO3 integration tests (py_to_json, json_to_py) are tested via Python tests
    // since they require linking to Python runtime which isn't available in cargo test.
}
