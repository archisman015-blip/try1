import streamlit as st
import pdfplumber
from gtts import gTTS
import tempfile
import os

st.title("📰 PDF to Audio Converter")

st.write("Upload a newspaper PDF (with selectable text). Scanned/image-only pages are ignored.")

uploaded_pdf = st.file_uploader("Upload PDF", type=["pdf"])

if uploaded_pdf:
    st.success("PDF uploaded successfully!")

    if st.button("Convert to MP3"):
        text_content = ""

        # Extract text from PDF
        with pdfplumber.open(uploaded_pdf) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text_content += extracted + "\n\n"

        if not text_content.strip():
            st.error("No selectable text found in this PDF. (Scanned PDFs will not work.)")
        else:
            st.subheader("Extracted Text (preview)")
            st.text_area("Preview", text_content[:3000], height=300)

            # Convert text to MP3 using gTTS
           # ---- Robust chunked gTTS generation (reliable on cloud) ----
import time
from gtts import gTTSError

def generate_gtts_parts(text: str, tmp_dir: str, max_chars_per_call: int = 2000, retries: int = 3, pause: float = 1.0):
    """
    Chunk text and create MP3 parts using gTTS. Returns list of file paths.
    - max_chars_per_call: conservative chunk size
    - retries: attempts per chunk
    """
    if not text:
        return []

    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    parts = []
    cur = ""
    for s in sentences:
        if len(cur) + len(s) + 1 > max_chars_per_call:
            if cur:
                parts.append(cur.strip())
            if len(s) > max_chars_per_call:
                for i in range(0, len(s), max_chars_per_call):
                    parts.append(s[i:i+max_chars_per_call].strip())
                cur = ""
            else:
                cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        parts.append(cur)

    out_paths = []
    for idx, chunk in enumerate(parts, start=1):
        out_path = os.path.join(tmp_dir, f"part_{idx:03d}.mp3")
        success = False
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                t = gTTS(chunk, lang='en')
                t.save(out_path)
                success = True
                break
            except gTTSError as e:
                last_err = e
                time.sleep(pause * attempt)
            except Exception as e:
                last_err = e
                time.sleep(pause * attempt)
        if not success:
            raise RuntimeError(f"gTTS failed for chunk {idx}: {last_err}")
        out_paths.append(out_path)
    return out_paths

with st.spinner("Converting to audio (chunked)..."):
    tmp_dir = tempfile.mkdtemp(prefix="tts_parts_")
    try:
        part_paths = generate_gtts_parts(text_content, tmp_dir)
    except Exception as e:
        st.error(f"Audio generation failed: {e}")
        print("gTTS error detail:", e)
        st.stop()

# Present results
if len(part_paths) == 1:
    with open(part_paths[0], "rb") as f:
        data = f.read()
    st.audio(data, format="audio/mp3")
    st.download_button("Download MP3", data=data, file_name=os.path.basename(part_paths[0]), mime="audio/mp3")
else:
    zip_name = os.path.join(tmp_dir, "audio_parts.zip")
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in part_paths:
            zf.write(p, arcname=os.path.basename(p))
    with open(zip_name, "rb") as f:
        zdata = f.read()
    st.download_button("Download all MP3 parts (.zip)", data=zdata, file_name="audio_parts.zip", mime="application/zip")

st.success("Done — audio ready.")


            # Load audio to display in Streamlit
            audio_bytes = open(tmp_file.name, "rb").read()

            st.audio(audio_bytes, format="audio/mp3")

            st.download_button(
                label="Download MP3",
                data=audio_bytes,
                file_name="output.mp3",
                mime="audio/mp3"
            )

            # Cleanup temp file
            os.remove(tmp_file.name)
            st.success("Conversion completed!")
