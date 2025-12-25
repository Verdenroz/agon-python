//! Type definitions and Python/JSON conversion utilities

use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString};
use serde_json::Value as SerdeValue;

use crate::error::{AgonError, Result};

/// Our JSON value type (re-export of serde_json::Value for convenience)
pub type JsonValue = SerdeValue;

/// Convert a Python object to a JSON Value
pub fn py_to_json(obj: &Bound<'_, PyAny>) -> Result<JsonValue> {
    if obj.is_none() {
        return Ok(JsonValue::Null);
    }

    // Check bool before int (bool is subclass of int in Python)
    if obj.is_instance_of::<PyBool>() {
        return Ok(JsonValue::Bool(obj.extract::<bool>()?));
    }

    if obj.is_instance_of::<PyInt>() {
        if let Ok(n) = obj.extract::<i64>() {
            return Ok(JsonValue::Number(n.into()));
        }
        // Try as float if i64 doesn't work (large numbers)
        if let Ok(f) = obj.extract::<f64>() {
            if let Some(n) = serde_json::Number::from_f64(f) {
                return Ok(JsonValue::Number(n));
            }
        }
        return Err(AgonError::InvalidData("Integer too large".to_string()));
    }

    if obj.is_instance_of::<PyFloat>() {
        let val: f64 = obj.extract().map_err(AgonError::from)?;
        if let Some(n) = serde_json::Number::from_f64(val) {
            return Ok(JsonValue::Number(n));
        }
        // Handle NaN/Infinity as null (JSON doesn't support them)
        return Ok(JsonValue::Null);
    }

    if obj.is_instance_of::<PyString>() {
        return Ok(JsonValue::String(obj.extract::<String>()?));
    }

    if obj.is_instance_of::<PyList>() {
        let list = obj
            .cast::<PyList>()
            .map_err(|e| AgonError::InvalidData(e.to_string()))?;
        let arr: Result<Vec<JsonValue>> = list.iter().map(|item| py_to_json(&item)).collect();
        return Ok(JsonValue::Array(arr?));
    }

    if obj.is_instance_of::<PyDict>() {
        let dict = obj
            .cast::<PyDict>()
            .map_err(|e| AgonError::InvalidData(e.to_string()))?;
        let mut map = serde_json::Map::new();
        for (key, value) in dict.iter() {
            let key_str = key
                .extract::<String>()
                .map_err(|_| AgonError::InvalidData("Dict keys must be strings".to_string()))?;
            map.insert(key_str, py_to_json(&value)?);
        }
        return Ok(JsonValue::Object(map));
    }

    // Try to convert via str() as fallback
    if let Ok(s) = obj.str() {
        return Ok(JsonValue::String(s.to_string()));
    }

    let type_name = obj
        .get_type()
        .name()
        .map(|n| n.to_string())
        .unwrap_or_else(|_| "unknown".to_string());
    Err(AgonError::InvalidData(format!(
        "Cannot convert {} to JSON",
        type_name
    )))
}

/// Convert a JSON Value to a Python object
pub fn json_to_py(py: Python<'_>, value: &JsonValue) -> PyResult<Py<PyAny>> {
    match value {
        JsonValue::Null => Ok(py.None()),
        JsonValue::Bool(b) => Ok(b.into_pyobject(py)?.to_owned().unbind().into_any()),
        JsonValue::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.into_pyobject(py)?.to_owned().unbind().into_any())
            } else if let Some(f) = n.as_f64() {
                Ok(f.into_pyobject(py)?.to_owned().unbind().into_any())
            } else {
                Ok(n.to_string().into_pyobject(py)?.unbind().into_any())
            }
        }
        JsonValue::String(s) => Ok(s.into_pyobject(py)?.unbind().into_any()),
        JsonValue::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(json_to_py(py, item)?)?;
            }
            Ok(list.unbind().into_any())
        }
        JsonValue::Object(map) => {
            let dict = PyDict::new(py);
            for (key, val) in map {
                dict.set_item(key, json_to_py(py, val)?)?;
            }
            Ok(dict.unbind().into_any())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_json_roundtrip() {
        let json = r#"{"name": "test", "values": [1, 2, 3], "nested": {"a": true}}"#;
        let value: JsonValue = serde_json::from_str(json).unwrap();
        let back = serde_json::to_string(&value).unwrap();
        assert!(back.contains("name"));
    }
}
