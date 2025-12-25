//! Error types for AGON encoding/decoding

use pyo3::exceptions::PyValueError;
use pyo3::PyErr;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum AgonError {
    #[error("Invalid AGON format: {0}")]
    InvalidFormat(String),

    #[error("Encoding error: {0}")]
    EncodingError(String),

    #[error("Decoding error: {0}")]
    DecodingError(String),

    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),

    #[error("Invalid data structure: {0}")]
    InvalidData(String),

    #[error("Parse error at line {line}: {message}")]
    ParseError { line: usize, message: String },

    #[error("Python error: {0}")]
    PyError(String),
}

impl From<AgonError> for PyErr {
    fn from(err: AgonError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

impl From<PyErr> for AgonError {
    fn from(err: PyErr) -> AgonError {
        AgonError::PyError(err.to_string())
    }
}

pub type Result<T> = std::result::Result<T, AgonError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_invalid_format_error() {
        let err = AgonError::InvalidFormat("unknown".to_string());
        assert_eq!(err.to_string(), "Invalid AGON format: unknown");
    }

    #[test]
    fn test_encoding_error() {
        let err = AgonError::EncodingError("failed to encode".to_string());
        assert_eq!(err.to_string(), "Encoding error: failed to encode");
    }

    #[test]
    fn test_decoding_error() {
        let err = AgonError::DecodingError("invalid payload".to_string());
        assert_eq!(err.to_string(), "Decoding error: invalid payload");
    }

    #[test]
    fn test_invalid_data_error() {
        let err = AgonError::InvalidData("bad structure".to_string());
        assert_eq!(err.to_string(), "Invalid data structure: bad structure");
    }

    #[test]
    fn test_parse_error() {
        let err = AgonError::ParseError {
            line: 42,
            message: "unexpected token".to_string(),
        };
        assert_eq!(err.to_string(), "Parse error at line 42: unexpected token");
    }

    #[test]
    fn test_py_error() {
        let err = AgonError::PyError("Python exception".to_string());
        assert_eq!(err.to_string(), "Python error: Python exception");
    }

    #[test]
    fn test_json_error_from() {
        // Create a JSON parse error
        let json_err = serde_json::from_str::<serde_json::Value>("invalid json").unwrap_err();
        let agon_err: AgonError = json_err.into();
        assert!(agon_err.to_string().contains("JSON error"));
    }

    #[test]
    fn test_error_debug_format() {
        let err = AgonError::InvalidFormat("test".to_string());
        let debug_str = format!("{:?}", err);
        assert!(debug_str.contains("InvalidFormat"));
    }
}
