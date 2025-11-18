import os
import re
import time
import io
import zipfile
import tempfile
import random
from typing import List

import streamlit as st
import pdfplumber
from gtts import gTTS, gTTSError

# ---------------- Helpers ----------------

def clean_extracted(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)        # join hyphenated words
    text = re.sub(r"\n(?=[^\n])", " ", text)            # single newlines -> space
    text = re.sub(r"\s+", " ", text)                    # collapse whitespace
    return text.strip()

def chunk_text_for_tts(text: str, max_chars: int = 1200) -> List[str]:
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    parts = []
    cur = ""
    for s in sentences:
        if len(cur) + len(s) + 1 > max_chars:
            if cur:
                parts.append(cur.strip())
            if len(s) > max_chars:
                # hard-split long sentence
                for i in range(0, len(s), max_chars):
                    parts.append(s[i:i+max_chars].strip())
                cur = ""
            else:
                cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        parts.append(cur)
    return parts

# ---- Hardened chunked gTTS generator (backoff, jitter, throttling) ----
def generate_gtts_parts(text: str,
                        tmp_dir: str,
                        max_chars_per_call: int = 1200,
                        retries: int = 6,
                        base_pause: float = 1.5,
                        jitter: float = 1.0,
                        per_chunk_delay: float = 0.8) -> List[str]:
    """
    Generate MP3 parts using gTTS with robust retry/backoff + jitter.
    - max_chars_per_call: smaller chunk size reduces chance of rejection.
    - retries: number of attempts per chunk.
    - base_pause: base backoff seconds (exponential).
    - jitter: max seconds of random jitter added to backoff.
    - per_chunk_delay: pause after a successful chunk to avoid bursts.
    """
    if not text:
        return []
    parts = chunk_text_for_tts(text, max_chars=max_chars_per_call)
    out_paths: List[str] = []

    for idx, chunk in enumerate(parts, start=1):
        out_path = os.path.join(tmp_dir, f"part_{idx:03d}.mp3")
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                t = gTTS(chunk, lang='en')
                t.save(out_path)
                # brief delay after success to avoid immediate bursts
                time.sleep(per_chunk_delay)
                out_paths.append(out_path)
                last_err = None
                break
            except gTTSError as e:
                last_err = e
                msg = str(e)
                if '429' in msg or 'Too Many Requests' in msg:
                    wait = base_pause * (2 ** attempt) + random.uniform(0, jitter * 2)
                else:
                    wait = base_pause * (2 ** (attempt - 1)) + random.uniform(0, jitter)
                print(f"[gTTS backoff] chunk {idx} attempt {attempt} failed: {e}. Backing off {wait:.1f}s")
                time.sleep(wait)
            except Exception as e:
                last_err = e
                wait = base_pause * (2 ** (attempt - 1)) + random.uniform(0, jitter)
                print(f"[gTTS error] chunk {idx} attempt {attempt} failed (exc): {e}. Backing off {wait:.1f}s")
                time.sleep(wait)
        if last_err is not None:
            raise RuntimeError(f"gTTS failed for chunk {idx} after {retries} attempts: {last_err}")
    return out_paths
# -------------------------------------------------------

# ---------------- Streamlit UI ----------------

st.set_page_config(page_title="PDF → Audio Converter", layout="centered")
st.title("📰 PDF → Audio Converter")
st.write("Upload a newspaper PDF (selectable text). Scanned/image-only pages are ignored — use OCR before upload for scanned PDFs.")

uploaded_pdf = st.file_uploader("Upload PDF", type=["pdf"])
if not uploaded_pdf:
    st.info("Upload a PDF file to begin.")
    st.stop()

if st.button("Convert to MP3"):
    # extract text
    text_content = ""
    try:
        with pdfplumber.open(uploaded_pdf) as pdf:
            for page in pdf.pages:
                ptext = page.extract_text() or ""
                if ptext.strip():
                    text_content += ptext + "\n\n"
    except Exception as e:
        st.error(f"Failed to read PDF: {e}")
        st.stop()

    text_content = clean_extracted(text_content)
    if not text_content:
        st.error("No selectable text found in the PDF. Scanned/image-only PDFs are ignored.")
        st.stop()

    st.subheader("Preview (first 3000 chars)")
    st.text_area("Preview", value=text_content[:3000], height=300)

    # choose chunk size (tune down if gTTS fails)
    max_chars = st.slider("Max chars per gTTS call", min_value=600, max_value=4000, value=1200, step=100)

    with st.spinner("Converting to audio (chunked, this may take some time)..."):
        tmp_dir = tempfile.mkdtemp(prefix="tts_parts_")
        try:
            part_paths = generate_gtts_parts(text_content, tmp_dir,
                                             max_chars_per_call=max_chars,
                                             retries=6,
                                             base_pause=1.5,
                                             jitter=1.0,
                                             per_chunk_delay=0.9)
        except Exception as e:
            st.error(f"Audio generation failed: {e}")
            print("gTTS error detail:", e)
            # cleanup partial files
            try:
                for f in os.listdir(tmp_dir):
                    os.remove(os.path.join(tmp_dir, f))
            except Exception:
                pass
            st.stop()

    if not part_paths:
        st.error("No audio parts were created.")
        st.stop()

    # Present results: single MP3 if only one part; otherwise provide zip of parts
    if len(part_paths) == 1:
        with open(part_paths[0], "rb") as f:
            data = f.read()
        st.audio(data, format="audio/mp3")
        st.download_button("Download MP3", data=data, file_name=os.path.basename(part_paths[0]), mime="audio/mp3")
    else:
        zip_path = os.path.join(tmp_dir, f"{os.path.splitext(uploaded_pdf.name)[0]}_mp3_parts.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in part_paths:
                zf.write(p, arcname=os.path.basename(p))
        with open(zip_path, "rb") as f:
            zdata = f.read()
        st.download_button("Download all MP3 parts (.zip)", data=zdata, file_name=os.path.basename(zip_path), mime="application/zip")
        # Optionally show first part in audio player
        with open(part_paths[0], "rb") as f:
            st.audio(f.read(), format="audio/mp3")

    st.success("Conversion completed. Download above.")
