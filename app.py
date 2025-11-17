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
            with st.spinner("Converting text to audio..."):
                tts = gTTS(text_content)
                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                tts.save(tmp_file.name)

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
