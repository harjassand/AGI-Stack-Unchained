use std::fmt;

#[derive(Debug)]
pub enum Base64Error {
    InvalidLength,
    InvalidChar,
    InvalidPadding,
}

impl fmt::Display for Base64Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Base64Error::InvalidLength => write!(f, "invalid base64 length"),
            Base64Error::InvalidChar => write!(f, "invalid base64 character"),
            Base64Error::InvalidPadding => write!(f, "invalid base64 padding"),
        }
    }
}

pub fn decode_base64(input: &str) -> Result<Vec<u8>, Base64Error> {
    let bytes = input.as_bytes();
    if bytes.len() % 4 != 0 {
        return Err(Base64Error::InvalidLength);
    }

    let mut out = Vec::with_capacity(bytes.len() / 4 * 3);
    let mut i = 0;
    while i < bytes.len() {
        let b0 = bytes[i];
        let b1 = bytes[i + 1];
        let b2 = bytes[i + 2];
        let b3 = bytes[i + 3];

        let v0 = decode_char(b0)?;
        let v1 = decode_char(b1)?;

        let v2 = if b2 == b'=' { 64 } else { decode_char(b2)? };
        let v3 = if b3 == b'=' { 64 } else { decode_char(b3)? };

        if v2 == 64 && v3 != 64 {
            return Err(Base64Error::InvalidPadding);
        }

        let n = ((v0 as u32) << 18) | ((v1 as u32) << 12) | ((v2 as u32) << 6) | (v3 as u32);

        out.push(((n >> 16) & 0xff) as u8);
        if v2 != 64 {
            out.push(((n >> 8) & 0xff) as u8);
        }
        if v3 != 64 {
            out.push((n & 0xff) as u8);
        }

        i += 4;
    }

    Ok(out)
}

fn decode_char(b: u8) -> Result<u8, Base64Error> {
    match b {
        b'A'..=b'Z' => Ok(b - b'A'),
        b'a'..=b'z' => Ok(26 + (b - b'a')),
        b'0'..=b'9' => Ok(52 + (b - b'0')),
        b'+' => Ok(62),
        b'/' => Ok(63),
        b'=' => Ok(64),
        _ => Err(Base64Error::InvalidChar),
    }
}
