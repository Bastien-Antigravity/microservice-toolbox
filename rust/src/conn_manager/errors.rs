use std::fmt;

#[derive(Debug)]
pub enum Error {
    ConnectionRefused(String),
    MaxRetriesReached(String),
    NoConnection(String),
    WriteFailed(String),
    Io(std::io::Error),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::ConnectionRefused(msg) => write!(f, "Connection refused: {}", msg),
            Error::MaxRetriesReached(msg) => write!(f, "Max retries reached: {}", msg),
            Error::NoConnection(msg) => write!(f, "No active connection: {}", msg),
            Error::WriteFailed(msg) => write!(f, "Write failed: {}", msg),
            Error::Io(err) => write!(f, "IO error: {}", err),
        }
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(err: std::io::Error) -> Self {
        Error::Io(err)
    }
}
