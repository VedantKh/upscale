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
# TARGET_SIZE = (10629, 15354) # Original hardcoded target size
TARGET_DPI_VALUE = 300 # Keep DPI as a single value for calculations
TARGET_DPI = (TARGET_DPI_VALUE, TARGET_DPI_VALUE) # For PIL save
API_SCALE = 4
CM_TO_INCH = 1 / 2.54

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

st.sidebar.header("Target Output Settings")
target_width_cm = st.sidebar.number_input("Target Width (cm)", min_value=1.0, value=26.99, step=0.1)
target_height_cm = st.sidebar.number_input("Target Height (cm)", min_value=1.0, value=38.99, step=0.1)
st.sidebar.info(f"Target DPI: {TARGET_DPI_VALUE}")

# Calculate target size in pixels
target_width_px = int(target_width_cm * CM_TO_INCH * TARGET_DPI_VALUE)
target_height_px = int(target_height_cm * CM_TO_INCH * TARGET_DPI_VALUE)
TARGET_SIZE = (target_width_px, target_height_px)

st.sidebar.write(f"Calculated Target Pixels: {target_width_px} × {target_height_px}")

uploaded_file = st.file_uploader("Upload an image (JPEG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file:
    # Save uploaded image to disk
    input_path = f"input_{uploaded_file.name}"
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    # Get or create client ID for this image name
    client_id = get_or_create_client_id_for_image(uploaded_file.name)
    st.caption(f"Session client ID for this image: `{client_id}` (auto-managed)")
    st.write("**[LOG] Image uploaded and client ID assigned.**")

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
    import math
    n_steps = math.ceil(math.log(scale_factor, API_SCALE))
    st.write(f"**Required upscaling steps (4x each):** {n_steps}")
    st.write(f"**[LOG] Calculated scale factor: {scale_factor:.2f}, steps needed: {n_steps}**")

    # --- API UPSCALING LOOP WITH PROGRESS BAR ---
    current_path = input_path
    progress = st.progress(0, text="Upscaling in progress...")
    for attempt in range(n_steps):
        st.write(f"**[LOG] Starting upscaling pass {attempt+1} of {n_steps}...**")
        progress.progress((attempt) / n_steps, text=f"Upscaling pass {attempt+1} of {n_steps} (4x)...")
        upload_image(current_path, client_id, scale=API_SCALE, use_face_enhance=False)
        st.write(f"**[LOG] Image sent to API for pass {attempt+1}. Waiting for processing...**")
        # Wait for completion
        upscaled_url = None
        with st.spinner(f"Waiting for API processing (pass {attempt+1})..."):
            for wait_idx in range(60):  # Wait up to 10 minutes
                _, completed, _ = get_uploaded_images(client_id)
                st.write(f"[LOG] Poll {wait_idx+1}/60: {len(completed)} completed images found.")
                if completed:
                    upscaled_url = completed[-1]["url"] if isinstance(completed[-1], dict) and "url" in completed[-1] else completed[-1]
                    st.write(f"**[LOG] Upscaled image URL received: {upscaled_url}**")
                    break
                time.sleep(10)
        if not upscaled_url:
            st.error("Upscaling failed or timed out.")
            st.stop()
        # Download upscaled image
        st.write(f"**[LOG] Downloading upscaled image for pass {attempt+1}...**")
        response = requests.get(upscaled_url)
        upscaled_path = f"upscaled_{attempt+1}_{uploaded_file.name}"
        with open(upscaled_path, "wb") as f:
            f.write(response.content)
        st.write(f"**[LOG] Upscaled image saved to {upscaled_path}.**")
        current_path = upscaled_path
    progress.progress(1.0, text="Upscaling complete!")
    st.write("**[LOG] All upscaling passes complete. Proceeding to local resize.**")

    # --- LOCAL RESIZE ---
    st.info("Resizing to target dimensions and setting DPI...")
    upscaled_img = Image.open(current_path)
    st.image(upscaled_img, caption="Upscaled", use_container_width=True)
    final_img = upscaled_img.resize(TARGET_SIZE, Image.LANCZOS)
    final_path = f"final_upscaled_{uploaded_file.name}"
    final_img.save(final_path, dpi=TARGET_DPI)
    st.write(f"**[LOG] Final image resized and saved to {final_path}.**")

    # --- DISPLAY FINAL IMAGE AND METADATA ---
    st.subheader("Upscaled Image (to 300 DPI)")
    st.image(final_img, caption="Upscaled and resized", use_container_width=True)
    st.write(f"**Dimensions:** {final_img.width} × {final_img.height}")
    st.write(f"**Format:** {final_img.format if final_img.format else 'JPEG'}")
    st.write(f"**Mode:** {final_img.mode}")
    st.write(f"**DPI:** {TARGET_DPI[0]} x {TARGET_DPI[1]}")
    st.write("**[LOG] Processing complete. Ready for download.**")

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