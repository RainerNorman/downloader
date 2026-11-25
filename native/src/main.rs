use std::env;
use std::fs::{File, OpenOptions};
use std::io::{self, BufWriter, Read, Seek, Write};
use std::path::Path;

const MAX_PAGES: usize = 1500;
const MAX_IMAGE_BYTES: u32 = 32 * 1024 * 1024;
const MAX_PIXELS: u64 = 25_000_000;

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

struct Pdf {
    out: BufWriter<File>,
    offsets: Vec<u64>,
}

impl Pdf {
    fn begin_object(&mut self) -> io::Result<()> {
        self.offsets.push(self.out.stream_position()?);
        writeln!(self.out, "{} 0 obj", self.offsets.len())
    }

    fn end_object(&mut self) -> io::Result<()> {
        writeln!(self.out, "endobj")
    }

    fn add_page(&mut self, input: &mut impl Read) -> io::Result<()> {
        // Python validates the JPEG. Each record is four little-endian u32s followed by its bytes.
        let mut header = [0u8; 16];
        input.read_exact(&mut header)?;
        let [width, height, channels, length] = std::array::from_fn(|index| {
            u32::from_le_bytes(header[index * 4..index * 4 + 4].try_into().unwrap())
        });
        let color_space = match channels {
            1 => "/DeviceGray",
            3 => "/DeviceRGB",
            _ => return Err(invalid("unsupported JPEG color space")),
        };
        if width == 0
            || height == 0
            || u64::from(width) * u64::from(height) > MAX_PIXELS
            || !(2..=MAX_IMAGE_BYTES).contains(&length)
        {
            return Err(invalid("invalid JPEG page metadata"));
        }

        self.begin_object()?;
        let image_id = self.offsets.len();
        writeln!(
            self.out,
            "<< /Type /XObject /Subtype /Image /Width {width} /Height {height} \
             /ColorSpace {color_space} /BitsPerComponent 8 /Filter /DCTDecode /Length {length} >>\nstream"
        )?;
        if io::copy(&mut input.take(u64::from(length)), &mut self.out)? != u64::from(length) {
            return Err(invalid("incomplete JPEG page"));
        }
        writeln!(self.out, "\nendstream")?;
        self.end_object()?;

        let scale = 842.0 / f64::from(width.max(height));
        let (page_width, page_height) = (f64::from(width) * scale, f64::from(height) * scale);
        let commands = format!("q {page_width:.6} 0 0 {page_height:.6} 0 0 cm /Im0 Do Q\n");
        self.begin_object()?;
        let content_id = self.offsets.len();
        writeln!(self.out, "<< /Length {} >>\nstream", commands.len())?;
        write!(self.out, "{commands}endstream\n")?;
        self.end_object()?;

        self.begin_object()?;
        writeln!(
            self.out,
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width:.6} {page_height:.6}] \
             /Resources << /XObject << /Im0 {image_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )?;
        self.end_object()
    }

    fn finish(mut self) -> io::Result<()> {
        let xref = self.out.stream_position()?;
        writeln!(
            self.out,
            "xref\n0 {}\n0000000000 65535 f ",
            self.offsets.len() + 1
        )?;
        for offset in &self.offsets {
            if *offset > 9_999_999_999 {
                return Err(invalid("PDF exceeds the cross-reference table size"));
            }
            writeln!(self.out, "{offset:010} 00000 n ")?;
        }
        writeln!(
            self.out,
            "trailer\n<< /Size {} /Root 1 0 R /Info 3 0 R >>\nstartxref\n{xref}\n%%EOF",
            self.offsets.len() + 1
        )?;
        self.out.flush()
    }
}

fn write_pdf(path: &Path, title: &str, count: usize, mut input: impl Read) -> io::Result<()> {
    if !(1..=MAX_PAGES).contains(&count) {
        return Err(invalid("invalid page count"));
    }
    let mut pdf = Pdf {
        out: BufWriter::new(OpenOptions::new().write(true).truncate(true).open(path)?),
        offsets: Vec::with_capacity(3 + count * 3),
    };
    pdf.out.write_all(b"%PDF-1.4\n%\xFF\xFF\xFF\xFF\n")?;
    pdf.begin_object()?;
    writeln!(pdf.out, "<< /Type /Catalog /Pages 2 0 R >>")?;
    pdf.end_object()?;

    pdf.begin_object()?;
    write!(pdf.out, "<< /Type /Pages /Count {count} /Kids [")?;
    for index in 0..count {
        write!(pdf.out, "{} 0 R ", 6 + index * 3)?;
    }
    writeln!(pdf.out, "] >>")?;
    pdf.end_object()?;

    pdf.begin_object()?;
    write!(pdf.out, "<< /Title <FEFF")?;
    for unit in title.encode_utf16() {
        write!(pdf.out, "{unit:04X}")?;
    }
    writeln!(pdf.out, "> >>")?;
    pdf.end_object()?;

    for _ in 0..count {
        pdf.add_page(&mut input)?;
    }
    pdf.finish()
}

fn main() -> io::Result<()> {
    let mut args = env::args_os().skip(1);
    let path = args.next().ok_or_else(|| invalid("missing output path"))?;
    let title = args.next().ok_or_else(|| invalid("missing title"))?;
    let count = args
        .next()
        .and_then(|arg| arg.to_str()?.parse().ok())
        .ok_or_else(|| invalid("missing or invalid page count"))?;
    if args.next().is_some() {
        return Err(invalid("unexpected arguments"));
    }
    write_pdf(Path::new(&path), &title.to_string_lossy(), count, io::stdin().lock())
}
