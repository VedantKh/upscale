import streamlit as st
from PIL import Image
import requests
import io
import time
import os
import secrets
import tempfile
import json
from image_upscaling_api import upload_image, get_uploaded_images

# --- CONFIG ---
TARGET_SIZE = (10629, 15354) # 130 cm x 90 cm
TARGET_DPI = (300, 300)
API_SCALE = 4

# --- CLIENT ID MANAGEMENT PER IMAGE ---
def get_or_create_client_id_for_image(image_name):
    temp_dir = tempfile.gettempdir()
    mapping_path = os.path.join(temp_dir, 'upscale_client_id_map.json')
    # Load or create the mapping
    if os.path.exists(mapping_path):
        with open(mapping_path, 'r') as f:
            try:
                mapping = json.load(f)
            except Exception:
                mapping = {}
    else:
        mapping = {}
    # Use the image name as the key
    if image_name in mapping and len(mapping[image_name]) == 32:
        return mapping[image_name]
    # Generate new 32-digit hex client ID
    client_id = secrets.token_hex(16)
    mapping[image_name] = client_id
    with open(mapping_path, 'w') as f:
        json.dump(mapping, f)
    return client_id

st.title("Image Upscaler (Auto 4x Steps) with image-upscaling.net API")

uploaded_file = st.file_uploader("Upload an image (JPEG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file:
    # Save uploaded image to disk
    input_path = f"input_{uploaded_file.name}"
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    # Get or create client ID for this image name
    client_id = get_or_create_client_id_for_image(uploaded_file.name)
    st.caption(f"Session client ID for this image: `{client_id}` (auto-managed)")

    # Show original image and metadata
    orig_img = Image.open(input_path)
    st.subheader("Original Image")
    st.image(orig_img, caption="Original", use_container_width=True)
    st.write(f"**Dimensions:** {orig_img.width} × {orig_img.height}")
    st.write(f"**Format:** {orig_img.format}")
    st.write(f"**Mode:** {orig_img.mode}")

    # --- DETERMINE UPSCALE STEPS ---
    width_scale = TARGET_SIZE[0] / orig_img.width
    height_scale = TARGET_SIZE[1] / orig_img.height
    scale_factor = max(width_scale, height_scale)
    # Each API_SCALE step multiplies by 4
    import math
    n_steps = math.ceil(math.log(scale_factor, API_SCALE))
    st.write(f"**Required upscaling steps (4x each):** {n_steps}")

    # --- API UPSCALING LOOP WITH PROGRESS BAR ---
    current_path = input_path
    progress = st.progress(0, text="Upscaling in progress...")
    for attempt in range(n_steps):
        progress.progress((attempt) / n_steps, text=f"Upscaling pass {attempt+1} of {n_steps} (4x)...")
        upload_image(current_path, client_id, scale=API_SCALE, use_face_enhance=False)
        # Wait for completion
        upscaled_url = None
        with st.spinner(f"Waiting for API processing (pass {attempt+1})..."):
            for _ in range(60):  # Wait up to 10 minutes
                _, completed, _ = get_uploaded_images(client_id)
                if completed:
                    upscaled_url = completed[-1]["url"] if isinstance(completed[-1], dict) and "url" in completed[-1] else completed[-1]
                    break
                time.sleep(10)
        if not upscaled_url:
            st.error("Upscaling failed or timed out.")
            st.stop()
        # Download upscaled image
        response = requests.get(upscaled_url)
        upscaled_path = f"upscaled_{attempt+1}_{uploaded_file.name}"
        with open(upscaled_path, "wb") as f:
            f.write(response.content)
        current_path = upscaled_path
    progress.progress(1.0, text="Upscaling complete!")

    # --- LOCAL RESIZE ---
    st.info("Resizing to target dimensions and setting DPI...")
    upscaled_img = Image.open(current_path)
    st.image(upscaled_img, caption="Upscaled", use_container_width=True)
    final_img = upscaled_img.resize(TARGET_SIZE, Image.LANCZOS)
    final_path = f"final_upscaled_{uploaded_file.name}"
    final_img.save(final_path, dpi=TARGET_DPI)

    # --- DISPLAY FINAL IMAGE AND METADATA ---
    st.subheader("Upscaled Image (to 300 DPI)")
    st.image(final_img, caption="Upscaled and resized", use_container_width=True)
    st.write(f"**Dimensions:** {final_img.width} × {final_img.height}")
    st.write(f"**Format:** {final_img.format if final_img.format else 'JPEG'}")
    st.write(f"**Mode:** {final_img.mode}")
    st.write(f"**DPI:** {TARGET_DPI[0]} x {TARGET_DPI[1]}")

    # --- DOWNLOAD BUTTON ---
    with open(final_path, "rb") as f:
        st.download_button(
            label="Download Upscaled Image (300 DPI)",
            data=f,
            file_name=f"upscaled_{os.path.splitext(uploaded_file.name)[0]}_300dpi.jpg",
            mime="image/jpeg"
        )
else:
    st.info("Please upload an image to begin.") 