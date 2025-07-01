#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# ---------- Standard library imports ----------
import os                    # For operating system file and folder handling
import sys                   # For system-specific parameters and functions
import json                  # For reading and writing JSON files
import zipfile              # For working with ZIP archives
import tempfile            # For creating temporary files and directories
import shutil              # For high-level file operations (copy, move, delete)
from io import BytesIO    # For in-memory binary streams
from collections import defaultdict  # For dictionary with default values
from pathlib import Path    # For modern object-oriented filesystem paths

# ---------- Web app framework ----------
import streamlit as st       # For creating interactive web applications

# ---------- Excel file handling ----------
import openpyxl             # For reading and writing Excel files (.xlsx)
from xlsxwriter import Workbook  # For creating more advanced Excel files

# ---------- Scientific computing ----------
import numpy as np          # For numerical computations and arrays
import pandas as pd         # For data analysis and table-like data structures
import matplotlib           # Core matplotlib configuration
import matplotlib.pyplot as plt  # For creating plots and figures
matplotlib.use("Agg")       # Use non-interactive backend (safe for headless servers)

# ---------- Computer vision and image processing ----------
import cv2                  # OpenCV for image processing and computer vision
from PIL import Image       # Pillow for general image reading and manipulation

# ---------- scikit-image modules ----------
from skimage.measure import label, regionprops   # For labeling and region property analysis
from skimage.filters import threshold_li         # Li's thresholding
from skimage.filters import threshold_otsu       # Otsu's thresholding
from skimage.filters import threshold_isodata    # Isodata thresholding
from skimage import data, filters, measure, morphology, exposure  # General image functions
from skimage.color import rgb2gray               # Convert RGB to grayscale
from skimage.morphology import opening, remove_small_objects, remove_small_holes, disk  # Morph operations
from skimage import color                         # Additional color space functions
from skimage.feature import peak_local_max        # Find local maxima
from skimage.segmentation import morphological_chan_vese  # Chan-Vese segmentation
from skimage.segmentation import slic             # Superpixel segmentation (SLIC)
from skimage.segmentation import active_contour   # Active contour segmentation
from skimage.segmentation import watershed        # Watershed segmentation
from skimage.io import imread                     # Image reading
from skimage.transform import resize              # Image resizing
from skimage import draw                          # Drawing shapes on images

# ---------- Scientific image processing with SciPy ----------
from scipy.ndimage import distance_transform_edt, label as ndi_label  # Distance transforms, labeling
from scipy import ndimage           # General n-dimensional image processing functions
from scipy.signal import find_peaks  # Find peaks in 1D data
import scipy.ndimage as ndi          # Alternative alias for ndimage (duplicate import, but sometimes used for shorter notation)

# ---------- Machine learning ----------
from sklearn.cluster import KMeans  # K-means clustering for segmentation or grouping

# Set Streamlit page configuration to wide layout
st.set_page_config(layout="wide")

# Set the app title
st.title("Microscopy Image Processing")

# Initialize a flag in session_state to handle reruns if not already present
if "rerun_flag" not in st.session_state:
    st.session_state.rerun_flag = False

# File uploader for BF images, allowing multiple .tif files
bf_files = st.file_uploader("Upload BF Images (.tif)", type=["tif"], accept_multiple_files=True)

# File uploader for PL images, allowing multiple .tif files
pl_files = st.file_uploader("Upload PL Images (.tif)", type=["tif"], accept_multiple_files=True)

# Sort uploaded BF files by filename
if bf_files:
    bf_files = sorted(bf_files, key=lambda x: x.name)

# Sort uploaded PL files by filename
if pl_files:
    pl_files = sorted(pl_files, key=lambda x: x.name)

# If both BF and PL files are uploaded
if bf_files and pl_files:
    # Show success message with counts
    st.success(f"Found {len(bf_files)} BF files and {len(pl_files)} PL files.")
    
    # Warn if number of BF and PL images do not match
    if len(bf_files) != len(pl_files):
        st.warning("The number of BF and PL images does not match. Only matching pairs will be processed.")

    # Display names of matching files to be processed
    for bf, pl in zip(bf_files, pl_files):
        st.write(f"Processing: {bf.name} and {pl.name}")

# Create output directory if it doesn't exist
output_dir = "outputs"
os.makedirs(output_dir, exist_ok=True)

# Define function to load saved scale settings from JSON file, cached by Streamlit
@st.cache_data
def load_scale_settings():
    try:
        with open('scale_map.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Default scale values if no file found
        return {"40": 5.64, "100": 13.89}

# Load the scale map from file or default
um_to_px_map = load_scale_settings()

# Sidebar header for scale settings
st.sidebar.header("Scale Settings")

# Dropdown to select known distance in µm
selected_um = st.sidebar.selectbox("Known Distance (µm):", list(um_to_px_map.keys()))

# Text input to specify pixel distance
distance_in_px = st.sidebar.text_input("Distance in Pixels:", value=str(um_to_px_map.get(selected_um, "")))

# Try to calculate pixel-to-µm conversion factor
try:
    s_um = float(selected_um)           # Known µm value
    d_px = float(distance_in_px)        # Entered pixel value
    PIXEL_TO_UM = 1 / (s_um / d_px)     # Calculate µm per pixel
    st.success(f"Calibration result: 1 px = {PIXEL_TO_UM:.4f} µm")
    st.session_state.pixel_to_um = PIXEL_TO_UM  # Save to session state
except ValueError:
    # Show error if values are invalid
    st.error("Please enter valid numeric values for scale calibration.")

# Add horizontal divider and new section in sidebar
st.sidebar.markdown("---")
st.sidebar.subheader("Manage Scale Settings")

# Sidebar inputs to add a new scale entry
new_um = st.sidebar.text_input("New µm value")
new_px = st.sidebar.text_input("New pixel value")

# Button to add new scale entry
if st.sidebar.button("➕ Add Scale"):
    try:
        new_um_f = float(new_um)                   # Convert µm to float
        new_px_f = float(new_px)                   # Convert px to float
        um_to_px_map[str(int(new_um_f))] = new_px_f  # Add to map with integer µm key
        with open('scale_map.json', 'w') as f:       # Save updated map to file
            json.dump(um_to_px_map, f, indent=4)
        st.sidebar.success(f"Added scale: {int(new_um_f)} µm = {new_px_f} px")
        st.cache_data.clear()                       # Clear Streamlit cache to reload data
        st.session_state.rerun_flag = not st.session_state.rerun_flag  # Toggle rerun flag
    except ValueError:
        st.sidebar.error("Enter valid numbers to add scale.")

# Dropdown to select a scale entry to delete
delete_um = st.sidebar.selectbox("Select µm to delete", list(um_to_px_map.keys()))

# Button to delete selected scale entry
if st.sidebar.button("🗑️ Delete Scale"):
    try:
        um_to_px_map.pop(delete_um, None)          # Remove selected entry
        with open('scale_map.json', 'w') as f:     # Save updated map
            json.dump(um_to_px_map, f, indent=4)
        st.sidebar.success(f"Deleted scale: {delete_um} µm")
        st.cache_data.clear()                      # Clear cache
        st.session_state.rerun_flag = not st.session_state.rerun_flag  # Toggle rerun
    except Exception as e:
        st.sidebar.error(f"Error deleting: {e}")

# ----------------- Session State Initialization -----------------

# Initialize session state flag to indicate if script 1 processing is done
if "script1_done" not in st.session_state:
    st.session_state.script1_done = False

# Initialize list to store results per BF/PL pair
if "script1_results" not in st.session_state:
    st.session_state.script1_results = []

# Initialize path for zip archive
if "zip_path_1" not in st.session_state:
    st.session_state.zip_path_1 = None

# ----------------- Start Button Logic -----------------

# Main button to start processing cells with crystals
if st.button("Number of cells with crystals"):
    if not bf_files or not pl_files:
        st.warning("Please upload both BF and PL files.")  # Warn if missing files
    elif len(bf_files) != len(pl_files):
        st.error("Mismatch in number of BF and PL files.")  # Error if file counts don't match
    else:
        st.session_state.script1_done = True  # Mark script as ready to run
        st.session_state.script1_results.clear()  # Clear previous results

# ----------------- Processing Logic -----------------

# If flagged, run the processing
if st.session_state.script1_done:
    st.write("🔄 Starting batch processing...")
    all_output_files = []  # List to collect generated file paths

    for bf_file, pl_file in zip(bf_files, pl_files):
        # Save uploaded files as temporary files
        with tempfile.NamedTemporaryFile(delete=False) as bf_temp, tempfile.NamedTemporaryFile(delete=False) as pl_temp:
            bf_temp.write(bf_file.read())
            pl_temp.write(pl_file.read())
            bf_path = bf_temp.name
            pl_path = pl_temp.name
        
        # Load images using OpenCV
        imageA = cv2.imread(bf_path)
        imageB = cv2.imread(pl_path)

        if imageA is None or imageB is None:
            st.warning(f"Unable to read {bf_file.name} or {pl_file.name}. Skipping...")
            continue

        # Convert BF image to grayscale
        grayA = rgb2gray(imageA)

        # Calculate crop margins to exclude bottom-right (scale bar region)
        h, w = grayA.shape
        crop_margin_h = int(0.015 * h)
        crop_margin_w = int(0.025 * w)

        # Mask to remove bottom-right area
        mask = np.ones_like(grayA, dtype=bool)
        mask[h - crop_margin_h:, w - crop_margin_w:] = False
        grayA = grayA * mask

        # Enhance contrast and filter noise
        grayA = exposure.equalize_adapthist(grayA)
        grayA = cv2.bilateralFilter((grayA * 255).astype(np.uint8), 9, 75, 75)
        threshold = threshold_otsu(grayA)
        binary_A = (grayA < threshold).astype(np.uint8) * 255

        # Morphological cleaning
        binary_A = morphology.opening(binary_A)
        binary_A = morphology.remove_small_objects(binary_A.astype(bool), min_size=500)
        binary_A = morphology.dilation(binary_A, morphology.disk(4))
        binary_A = morphology.remove_small_holes(binary_A, area_threshold=5000)
        binary_A = morphology.closing(binary_A, morphology.disk(4))
        binary_A = (binary_A > 0).astype(np.uint8) * 255

        # Label regions
        region_labels_A = label(binary_A)
        region_props_A = regionprops(region_labels_A)

        # Crop mask for bottom-right
        crop_start_row = h - crop_margin_h
        crop_start_col = w - crop_margin_w
        crop_mask = np.zeros_like(region_labels_A, dtype=bool)
        crop_mask[crop_start_row:, crop_start_col:] = True

        # Filter regions that overlap with crop area
        filtered_labels = []
        for region in region_props_A:
            region_mask = (region_labels_A == region.label)
            if np.any(region_mask & crop_mask):
                continue
            filtered_labels.append(region.label)

        # Create new labeled image excluding unwanted regions
        new_label_img = np.zeros_like(region_labels_A, dtype=np.int32)
        label_counter = 1
        for lbl in filtered_labels:
            new_label_img[region_labels_A == lbl] = label_counter
            label_counter += 1

        region_labels_A = new_label_img
        region_props_A = regionprops(region_labels_A)

        # Compute region areas and thresholds
        areas = [region.area for region in region_props_A]
        mean_area = np.mean(areas)
        median_area = np.median(areas)
        std_area = np.std(areas)
        average = median_area + std_area

        # Save histogram of areas
        fig, ax = plt.subplots()
        ax.hist(areas, bins=20, color='skyblue', edgecolor='black')
        hist_path_Areas = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Histogram_Areas.png")
        fig.savefig(hist_path_Areas)
        all_output_files.append(hist_path_Areas)

        # Refine regions: split large ones using watershed
        for region in region_props_A:
            if region.area < average:
                new_label_img[region.slice][region.image] = label_counter
                label_counter += 1
            else:
                region_mask = np.zeros_like(region_labels_A, dtype=np.uint8)
                region_mask[region.slice][region.image] = 1
                distance = ndi.distance_transform_edt(region_mask)
                coordinates = peak_local_max(distance, labels=region_mask, min_distance=5)
                local_maxi = np.zeros_like(distance, dtype=bool)
                local_maxi[tuple(coordinates.T)] = True
                markers = label(local_maxi)
                labels_ws = watershed(-distance, markers, mask=region_mask)
                for ws_label in np.unique(labels_ws):
                    if ws_label == 0:
                        continue
                    mask = labels_ws == ws_label
                    new_label_img[mask] = label_counter
                    label_counter += 1

        region_labels_A = new_label_img
        region_props_A = regionprops(region_labels_A)

        # Resize binary if needed
        if binary_A.shape != grayA.shape:
            binary_A = resize(binary_A, grayA.shape, order=0, preserve_range=True, anti_aliasing=False)

        # Create overlay image for annotation
        overlay_image = cv2.cvtColor((binary_A > 0).astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)
        for region in regionprops(region_labels_A):
            y, x = region.centroid
            label_id = region.label
            cv2.putText(overlay_image, str(label_id), (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

        annotated_path = os.path.join(output_dir, f"{bf_file.name}_Segmented_Cells.png")
        cv2.imwrite(annotated_path, overlay_image)
        all_output_files.append(annotated_path)

        # Save region area data
        region_area_df = pd.DataFrame({
            "Region_Label": [r.label for r in region_props_A],
            "Region_Area (pixels)": [r.area for r in region_props_A],
            "Region_Area (µm²)": [r.area * (PIXEL_TO_UM ** 2) for r in region_props_A]
        })
        region_area_df = region_area_df[region_area_df["Region_Area (µm²)"] > 0]
        total_cells = region_area_df["Region_Label"].count()
        region_area_df.loc["Total Area"] = ["", "Total Area", region_area_df["Region_Area (µm²)"].sum()]
        region_area_df.loc["Total Cells"] = ["", "Total Cells", total_cells]
        excel_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Region_Area.xlsx")
        region_area_df.to_excel(excel_path, index=False)

        # Save histogram of intensity
        fig, ax = plt.subplots()
        ax.hist(grayA.ravel(), bins=256, range=[0, 255])
        ax.axvline(threshold, color='red', linestyle='--')
        hist_path_A = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Histogram_A.png")
        fig.savefig(hist_path_A)
        all_output_files.append(hist_path_A)

        # Process PL image thresholding
        grayB = rgb2gray(imageB)
        grayB = exposure.equalize_adapthist(grayB)
        grayB = cv2.bilateralFilter((grayB * 255).astype(np.uint8), 9, 75, 75)
        mean_intensity = np.mean(grayB)
        std_intensity = np.std(grayB)
        dynamic_threshold = mean_intensity + 4 * std_intensity
        binary_B = (grayB > dynamic_threshold).astype(np.uint8)

        fig, ax = plt.subplots()
        ax.hist(grayB.ravel(), bins=256, range=[0, 255])
        ax.axvline(dynamic_threshold, color='red', linestyle='--')
        hist_path_B = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Histogram_B.png")
        fig.savefig(hist_path_B)
        all_output_files.append(hist_path_B)

        # Compute overlap between binary_A and binary_B
        overlap = (np.logical_and(cv2.resize(binary_A, (2048, 2048)) > 0, cv2.resize(binary_B, (2048, 2048)) > 0)).astype(np.uint8) * 255

        # Mask bottom-right to remove scale bar artifacts
        h2, w2 = overlap.shape
        overlap[h2-60:h2, w2-450:w2] = 0

        overlap_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Overlap.png")
        cv2.imwrite(overlap_path, overlap)
        all_output_files.append(overlap_path)

        # ----------------- Mapping crystals to cells -----------------
        region_props = regionprops(label(overlap))
        cell_props = region_props_A
        crystal_to_cell = []
        cell_to_crystals = defaultdict(list)

        for region in region_props:
            region_coords = set(map(tuple, region.coords))
            best_match_cell = None
            max_overlap = 0
            for cell in cell_props:
                cell_coords = set(map(tuple, cell.coords))
                overlap_area = len(region_coords & cell_coords)
                if overlap_area > 0:
                    cell_to_crystals[cell.label].append(region.label)
                if overlap_area > max_overlap:
                    max_overlap = overlap_area
                    best_match_cell = cell.label
            crystal_to_cell.append({
                "Region_Label": region.label,
                "Associated_Cell": best_match_cell,
                "Overlap (pixels)": max_overlap,
                "Region_Area (pixels)": region.area,
                "Region_Area (µm²)": region.area * (PIXEL_TO_UM ** 2)
            })

        df_mapping = pd.DataFrame(crystal_to_cell)

        # Print columns to debug
        print("df_mapping columns:", df_mapping.columns.tolist())
        print(df_mapping.head())  # Optional: show first rows

        expected_columns = ["Region_Label", "Associated_Cell", "Overlap (pixels)", "Region_Area (pixels)", "Region_Area (µm²)"]
        missing_cols = [col for col in expected_columns if col not in df_mapping.columns]
        if missing_cols:
            st.error(f"Missing columns in df_mapping: {missing_cols}")
            st.stop()

        df_mapping = df_mapping[(df_mapping["Region_Area (µm²)"] < 10) & (df_mapping["Overlap (pixels)"] > 0)]

        #if "Region_Area (µm²)" in df_mapping.columns:
        #    df_mapping = df_mapping[(df_mapping["Region_Area (µm²)"] < 10) & (df_mapping["Overlap (pixels)"] > 0)]
        #else:
        #    st.warning("⚠️ Column 'Region_Area (µm²)' missing in df_mapping — skipping filtering step.")

        df_mapping["Associated_Cell_Count"] = df_mapping["Associated_Cell"].map(df_mapping["Associated_Cell"].value_counts())
        df_mapping["Total_Cells_with_crystals"] = df_mapping["Associated_Cell"].nunique()
        df_mapping.loc["Total"] = ["", "", "", "Total Area Crystals", df_mapping["Region_Area (µm²)"].sum(), "", ""]

        cell_crystal_df = pd.DataFrame([
            {
                "Cell_Label": cell_label,
                "Crystal_Labels": ", ".join(map(str, set(crystals))),
                "Crystal_Count": len(set(crystals))
            }
            for cell_label, crystals in cell_to_crystals.items()
        ])
        
        merged_df = df_mapping.merge(region_area_df, left_on="Associated_Cell", right_on="Region_Label", how="inner")

        grouped_xlsx_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_All_Datasets.xlsx")
        with pd.ExcelWriter(grouped_xlsx_path, engine="xlsxwriter") as writer:
            region_area_df.to_excel(writer, sheet_name="Cells", index=False)
            df_mapping.to_excel(writer, sheet_name="Crystals", index=False)
            merged_df.to_excel(writer, sheet_name="Cells + Crystals", index=False)
            cell_crystal_df.to_excel(writer, sheet_name="Cell-Crystal Map", index=False)

        # Annotate final image
        annotated_image = cv2.cvtColor(imageA, cv2.COLOR_GRAY2BGR) if imageA.ndim == 2 else imageA.copy()
        for _, mapping in df_mapping.iterrows():
            if pd.notna(mapping["Associated_Cell"]):
                region = next((r for r in region_props if r.label == mapping["Region_Label"]), None)
                if region:
                    min_row, min_col, max_row, max_col = region.bbox
                    cv2.rectangle(annotated_image, (min_col, min_row), (max_col, max_row), (0, 255, 0), 2)
                    cv2.putText(annotated_image, f"Cell {int(mapping['Associated_Cell'])}", (min_col, max(min_row - 5, 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1, lineType=cv2.LINE_AA)

        annotated_image_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Annotated.png")
        cv2.imwrite(annotated_image_path, annotated_image)
        all_output_files.append(annotated_image_path)

        # Save session results
        st.session_state.script1_results.append({
            "bf_name": bf_file.name,
            "excel_path": grouped_xlsx_path,
            "annotated_img_path": annotated_image_path,
            "overlap_path": overlap_path,
            "hist_A_path": hist_path_A,
            "hist_B_path": hist_path_B,
        })

    # Create zip archive of all outputs
    zip_path_1 = os.path.join(output_dir, "All_Images_histograms.zip")
    with zipfile.ZipFile(zip_path_1, 'w') as zipf_1:
        for file_path in all_output_files:
            zipf_1.write(file_path, arcname=os.path.basename(file_path))
    st.session_state.zip_path_1 = zip_path_1
    st.success("✅ Processing complete!")

# ----------------- Display Outputs -----------------

if st.session_state.script1_results:
    st.header("📦 Results")

    for result1 in st.session_state.script1_results:
        st.subheader(f"📁 {result1['bf_name']}")
        st.image(result1["annotated_img_path"], caption="Detections crystals")
        st.image(result1["overlap_path"], caption="Correlation")
        with open(result1["excel_path"], "rb") as f1:
            st.download_button("📊 Download Dataset", f1, file_name=os.path.basename(result1["excel_path"]), key=f"download_button_{result1['bf_name']}_{os.path.basename(result1['excel_path'])}")

    with open(st.session_state.zip_path_1, "rb") as zf_1:
        st.download_button("🗂️ Download All Images and Histograms", zf_1, file_name="All_Images_histograms.zip")

# -------------------- Session State Initialization --------------------

# Check if "script2_done" exists in Streamlit session state; if not, initialize to False
if "script2_done" not in st.session_state:
    st.session_state.script2_done = False

# Initialize storage for results if not yet present
if "script2_results" not in st.session_state:
    st.session_state.script2_results = []

# Initialize ZIP archive path if not yet present
if "zip_path_2" not in st.session_state:
    st.session_state.zip_path_2 = None

# -------------------- Start Button --------------------

# Button to start area analysis
if st.button("Areas"):
    # Check if BF and PL files are uploaded
    if not bf_files or not pl_files:
        st.warning("Please upload both BF and PL files.")
    # Check if both file lists have equal length
    elif len(bf_files) != len(pl_files):
        st.error("Mismatch in number of BF and PL files.")
    else:
        # Set flag to start processing and clear previous results
        st.session_state.script2_done = True
        st.session_state.script2_results.clear()

# -------------------- Processing Logic --------------------

# Start processing if flag is True
if st.session_state.script2_done:
    st.write("🔄 Starting batch processing...")
    all_output_files = []  # Store all file paths for ZIP

    # Process each BF and PL file pair
    for bf_file, pl_file in zip(bf_files, pl_files):
        # Create temporary files for reading
        with tempfile.NamedTemporaryFile(delete=False) as bf_temp, tempfile.NamedTemporaryFile(delete=False) as pl_temp:
            bf_temp.write(bf_file.read())
            pl_temp.write(pl_file.read())
            bf_path = bf_temp.name
            pl_path = pl_temp.name

        # Load images from paths
        imageA = cv2.imread(bf_path)
        imageB = cv2.imread(pl_path)

        # Skip files if any image failed to load
        if imageA is None or imageB is None:
            st.warning(f"Unable to read {bf_file.name} or {pl_file.name}. Skipping...")
            continue

        # Convert BF image to grayscale
        grayA = rgb2gray(imageA)

        # Get image dimensions
        h, w = grayA.shape
        # Define margins for bottom-right scale bar
        crop_margin_h = int(0.015 * h)
        crop_margin_w = int(0.025 * w)

        # Create mask to exclude bottom-right region
        mask = np.ones_like(grayA, dtype=bool)
        mask[h - crop_margin_h:, w - crop_margin_w:] = False
        grayA = grayA * mask  # Mask out scale bar

        # Enhance contrast using CLAHE
        grayA = exposure.equalize_adapthist(grayA)
        # Smooth image with bilateral filter
        grayA = cv2.bilateralFilter((grayA * 255).astype(np.uint8), 9, 75, 75)
        # Compute Otsu threshold
        threshold = threshold_otsu(grayA)
        # Create binary mask (inverted)
        binary_A = (grayA < threshold).astype(np.uint8) * 255

        # Morphological opening to remove noise
        binary_A = morphology.opening(binary_A)
        # Remove small objects
        binary_A = morphology.remove_small_objects(binary_A.astype(bool), min_size=500)
        # Dilate mask to merge close regions
        binary_A = morphology.dilation(binary_A, morphology.disk(4))
        # Remove small holes
        binary_A = morphology.remove_small_holes(binary_A, area_threshold=5000)
        # Morphological closing to smooth regions
        binary_A = morphology.closing(binary_A, morphology.disk(4))
        # Convert to uint8 binary
        binary_A = (binary_A > 0).astype(np.uint8) * 255

        # Label connected components
        region_labels_A = label(binary_A)
        region_props_A = regionprops(region_labels_A)

        # Define start of bottom-right crop area
        crop_start_row = h - crop_margin_h
        crop_start_col = w - crop_margin_w

        filtered_labels = []  # Store valid region labels

        # Create crop mask for excluded area
        crop_mask = np.zeros_like(region_labels_A, dtype=bool)
        crop_mask[crop_start_row:, crop_start_col:] = True

        # Filter out regions touching crop area
        for region in region_props_A:
            region_mask = (region_labels_A == region.label)
            if np.any(region_mask & crop_mask):
                continue
            filtered_labels.append(region.label)

        # Create new labeled image with only filtered regions
        new_label_img = np.zeros_like(region_labels_A, dtype=np.int32)
        label_counter = 1
        for lbl in filtered_labels:
            new_label_img[region_labels_A == lbl] = label_counter
            label_counter += 1

        # Update labels and props after filtering
        region_labels_A = new_label_img
        region_props_A = regionprops(region_labels_A)

        # Calculate region areas
        areas = [region.area for region in region_props_A]
        mean_area = np.mean(areas)
        median_area = np.median(areas)
        std_area = np.std(areas)
        average = median_area + std_area  # Define area threshold

        # Plot histogram of region areas
        fig, ax = plt.subplots()
        ax.hist(areas, bins=20, color='skyblue', edgecolor='black')
        hist_path_Areas = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Histogram_Areas.png")
        fig.savefig(hist_path_Areas)
        all_output_files.append(hist_path_Areas)

        # Refine large regions with watershed
        for region in region_props_A:
            if region.area < average:
                new_label_img[region.slice][region.image] = label_counter
                label_counter += 1
            else:
                region_mask = np.zeros_like(region_labels_A, dtype=np.uint8)
                region_mask[region.slice] = region.image.astype(np.uint8)

                distance = distance_transform_edt(region_mask)
                coordinates = peak_local_max(distance, labels=region_mask, min_distance=5)
                local_maxi = np.zeros_like(distance, dtype=bool)
                local_maxi[tuple(coordinates.T)] = True
                markers = label(local_maxi)
                labels_ws = watershed(-distance, markers, mask=region_mask)

                for ws_label in np.unique(labels_ws):
                    if ws_label == 0:
                        continue
                    mask = labels_ws == ws_label
                    new_label_img[mask] = label_counter
                    label_counter += 1

        # Update final labels and props
        region_labels_A = new_label_img
        region_props_A = regionprops(region_labels_A)

        # Resize binary mask if needed
        if binary_A.shape != grayA.shape:
            binary_A = resize(binary_A, grayA.shape, order=0, preserve_range=True, anti_aliasing=False)

        # Create RGB overlay image for annotation
        overlay_image = cv2.cvtColor((binary_A > 0).astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)

        # Annotate regions with label numbers
        for region in regionprops(region_labels_A):
            y, x = region.centroid
            cv2.putText(overlay_image, str(region.label), (int(x), int(y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

        # Save annotated cells image
        annotated_path = os.path.join(output_dir, f"{bf_file.name}_Segmented_Cells.png")
        cv2.imwrite(annotated_path, overlay_image)
        all_output_files.append(annotated_path)

        # Create DataFrame with region areas
        region_area_df = pd.DataFrame({
            "Region_Label": [r.label for r in region_props_A],
            "Region_Area (pixels)": [r.area for r in region_props_A],
            "Region_Area (µm²)": [r.area * (PIXEL_TO_UM ** 2) for r in region_props_A]
        })

        # Filter regions with non-zero area
        region_area_df = region_area_df[region_area_df["Region_Area (µm²)"] > 0]
        total_cells = region_area_df["Region_Label"].count()
        region_area_df.loc["Total Area"] = ["", "Total Area", region_area_df["Region_Area (µm²)"].sum()]
        region_area_df.loc["Total Cells"] = ["", "Total Cells", total_cells]

        # Save Excel file with area data
        excel_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Region_Area.xlsx")
        region_area_df.to_excel(excel_path, index=False)

        # Plot histogram of pixel intensities for BF
        fig, ax = plt.subplots()
        ax.hist(grayA.ravel(), bins=256, range=[0, 255])
        ax.axvline(threshold, color='red', linestyle='--')
        hist_path_A = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Histogram_A.png")
        fig.savefig(hist_path_A)
        all_output_files.append(hist_path_A)

        # Process PL image: convert, enhance, and threshold
        grayB = rgb2gray(imageB)
        grayB = exposure.equalize_adapthist(grayB)
        grayB = cv2.bilateralFilter((grayB * 255).astype(np.uint8), 9, 75, 75)
        mean_intensity = np.mean(grayB)
        std_intensity = np.std(grayB)
        dynamic_threshold = mean_intensity + 4.6 * std_intensity
        binary_B = (grayB > dynamic_threshold).astype(np.uint8)
        binary_B = opening(binary_B)
        binary_B = (binary_B > 0).astype(np.uint8) * 255

        # Plot histogram of PL intensities
        fig, ax = plt.subplots()
        ax.hist(grayB.ravel(), bins=256, range=[0, 255])
        ax.axvline(dynamic_threshold, color='red', linestyle='--')
        hist_path_B = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Histogram_B.png")
        fig.savefig(hist_path_B)
        all_output_files.append(hist_path_B)

        # Compute overlap mask
        overlap = (np.logical_and(cv2.resize(binary_A, (2048, 2048)) > 0, cv2.resize(binary_B, (2048, 2048)) > 0)).astype(np.uint8) * 255

        # Mask out bottom-right scale bar area
        h2, w2 = overlap.shape
        overlap[h2 - 60:h2, w2 - 450:w2] = 0

        # Save overlap image
        overlap_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Overlap.png")
        cv2.imwrite(overlap_path, overlap)
        all_output_files.append(overlap_path)

        # Initialize region-to-cell mapping
        region_props = regionprops(label(overlap))
        cell_props = region_props_A
        crystal_to_cell = []
        cell_to_crystals = defaultdict(list)

        # Match each crystal region to a cell
        for region in region_props:
            region_coords = set(map(tuple, region.coords))
            best_match_cell = None
            max_overlap = 0
            for cell in cell_props:
                cell_coords = set(map(tuple, cell.coords))
                overlap_area = len(region_coords & cell_coords)
                if overlap_area > 0:
                    cell_to_crystals[cell.label].append(region.label)
                if overlap_area > max_overlap:
                    max_overlap = overlap_area
                    best_match_cell = cell.label
            crystal_to_cell.append({
                "Region_Label": region.label,
                "Associated_Cell": best_match_cell,
                "Overlap (pixels)": max_overlap,
                "Region_Area (pixels)": region.area,
                "Region_Area (µm²)": region.area * (PIXEL_TO_UM ** 2)
            })
            if best_match_cell is not None:
                cell_to_crystals[best_match_cell].append(region.label)

        # Create DataFrame for crystal mapping
        df_mapping = pd.DataFrame(crystal_to_cell)
        df_mapping = df_mapping[(df_mapping["Region_Area (µm²)"] < 6) & (df_mapping["Overlap (pixels)"] > 0)]
        df_mapping["Associated_Cell_Count"] = df_mapping["Associated_Cell"].map(df_mapping["Associated_Cell"].value_counts())
        df_mapping["Total_Cells_with_crystals"] = df_mapping["Associated_Cell"].nunique()
        df_mapping.loc["Total"] = ["", "", "", "Total Area Crystals", df_mapping["Region_Area (µm²)"].sum(), "", ""]

        # Create DataFrame mapping cells to crystals
        cell_crystal_df = pd.DataFrame([
            {"Cell_Label": cell_label,
             "Crystal_Labels": ", ".join(map(str, set(crystals))),
             "Crystal_Count": len(set(crystals))}
            for cell_label, crystals in cell_to_crystals.items()
        ])

        # Merge DataFrames for combined analysis
        merged_df = df_mapping.merge(region_area_df, left_on="Associated_Cell", right_on="Region_Label", how="inner")
        merged_df["Crystal/Cell Area (%)"] = pd.NA
        merged_df.loc[:-3, "Crystal/Cell Area (%)"] = (
            merged_df.loc[:-3, "Region_Area (µm²)_x"] / merged_df.loc[:-3, "Region_Area (µm²)_y"] * 100
        )

        # Save final Excel workbook with multiple sheets
        grouped_xlsx_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_All_Datasets.xlsx")
        with pd.ExcelWriter(grouped_xlsx_path, engine="xlsxwriter") as writer:
            region_area_df.to_excel(writer, sheet_name="Cells", index=False)
            df_mapping.to_excel(writer, sheet_name="Crystals", index=False)
            merged_df.to_excel(writer, sheet_name="Cells + Crystals", index=False)
            cell_crystal_df.to_excel(writer, sheet_name="Cell-Crystal Map", index=False)

        # Create annotated image with crystal-cell associations
        annotated_image = cv2.cvtColor(imageA, cv2.COLOR_GRAY2BGR) if imageA.ndim == 2 else imageA.copy()
        for _, mapping in df_mapping.iterrows():
            if pd.notna(mapping["Associated_Cell"]):
                region = next((r for r in region_props if r.label == mapping["Region_Label"]), None)
                if region:
                    min_row, min_col, max_row, max_col = region.bbox
                    cv2.rectangle(annotated_image, (min_col, min_row), (max_col, max_row), (0, 255, 0), 2)
                    cv2.putText(annotated_image, f"Cell {int(mapping['Associated_Cell'])}",
                                (min_col, max(min_row - 5, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                                (255, 0, 0), 1, cv2.LINE_AA)

        # Save final annotated image
        annotated_image_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Annotated.png")
        cv2.imwrite(annotated_image_path, annotated_image)
        all_output_files.append(annotated_image_path)

        # Store result in session state
        st.session_state.script2_results.append({
            "bf_name": bf_file.name,
            "excel_path": grouped_xlsx_path,
            "annotated_img_path": annotated_image_path,
            "overlap_path": overlap_path,
            "hist_A_path": hist_path_A,
            "hist_B_path": hist_path_B,
        })

    # Create ZIP archive of all outputs
    zip_path_2 = os.path.join(output_dir, "All_Images_histograms.zip")
    with zipfile.ZipFile(zip_path_2, 'w') as zipf_2:
        for file_path in all_output_files:
            zipf_2.write(file_path, arcname=os.path.basename(file_path))
    st.session_state.zip_path_2 = zip_path_2
    st.success("✅ Processing complete!")

# -------------------- Display Outputs and Downloads --------------------

# Display results if available
if st.session_state.script2_results:
    st.header("📦 Results")
    for result2 in st.session_state.script2_results:
        st.subheader(f"📁 {result2['bf_name']}")
        st.image(result2["annotated_img_path"], caption="Detection crystals")
        st.image(result2["overlap_path"], caption="Correlation")

        with open(result2["excel_path"], "rb") as f2:
            st.download_button("📊 Download Dataset", f2,
                               file_name=os.path.basename(result2["excel_path"]),
                               key=f"download_button_{result2['bf_name']}_{os.path.basename(result2['excel_path'])}")

    with open(st.session_state.zip_path_2, "rb") as zf_2:
        st.download_button("🗂️ Download All Images and Histograms", zf_2, file_name="All_Images_histograms.zip")

# -------------------- Session State Initialization --------------------

# Initialize flag to track if Script 3 has finished
if "script3_done" not in st.session_state:
    st.session_state.script3_done = False

# Initialize results list for Script 3
if "script3_results" not in st.session_state:
    st.session_state.script3_results = []

# Initialize ZIP path for Script 3 outputs
if "zip_path_3" not in st.session_state:
    st.session_state.zip_path_3 = None

# -------------------- Start Button --------------------

# Button to trigger cell number analysis
if st.button("Number of cells"):
    # Check if both BF and PL files have been uploaded
    if not bf_files or not pl_files:
        st.warning("Please upload both BF and PL files.")
    # Check if BF and PL lists have the same number of files
    elif len(bf_files) != len(pl_files):
        st.error("Mismatch in number of BF and PL files.")
    else:
        # Mark Script 3 as ready to process and clear previous results
        st.session_state.script3_done = True
        st.session_state.script3_results.clear()

# -------------------- Processing Logic --------------------

# Only run if Script 3 flag is set
if st.session_state.script3_done:
    st.write("🔄 Starting batch processing...")
    all_output_files = []  # List to store file paths for zip

    # Iterate over BF and PL file pairs
    for bf_file, pl_file in zip(bf_files, pl_files):
        # Save uploaded files as temporary files
        with tempfile.NamedTemporaryFile(delete=False) as bf_temp, tempfile.NamedTemporaryFile(delete=False) as pl_temp:
            bf_temp.write(bf_file.read())
            pl_temp.write(pl_file.read())
            bf_path = bf_temp.name
            pl_path = pl_temp.name

        # Read BF and PL images
        imageA = cv2.imread(bf_path)
        imageB = cv2.imread(pl_path)

        # Skip if either image cannot be loaded
        if imageA is None or imageB is None:
            st.warning(f"Unable to read {bf_file.name} or {pl_file.name}. Skipping...")
            continue

        # Convert BF image to grayscale
        grayA = rgb2gray(imageA)

        # ---------------- Crop scale bar region ----------------
        h, w = grayA.shape  # Get height and width
        crop_margin_h = int(0.015 * h)  # ~1.5% of height
        crop_margin_w = int(0.025 * w)  # ~2.5% of width

        # Create mask excluding bottom-right corner
        mask = np.ones_like(grayA, dtype=bool)
        mask[h - crop_margin_h:, w - crop_margin_w:] = False
        grayA = grayA * mask  # Zero out scale bar

        # Apply adaptive histogram equalization
        grayA = exposure.equalize_adapthist(grayA)
        # Apply bilateral filter to reduce noise
        grayA = cv2.bilateralFilter((grayA * 255).astype(np.uint8), 9, 75, 75)
        # Compute Otsu threshold
        threshold = threshold_otsu(grayA)
        # Create binary mask (inverted)
        binary_A = (grayA < threshold).astype(np.uint8) * 255

        # ---------------- Morphological Cleaning ----------------
        binary_A = morphology.opening(binary_A)  # Remove small noise
        binary_A = morphology.remove_small_objects(binary_A.astype(bool), min_size=500)
        binary_A = morphology.dilation(binary_A, morphology.disk(4))  # Connect regions
        binary_A = morphology.remove_small_holes(binary_A, area_threshold=5000)
        binary_A = morphology.closing(binary_A, morphology.disk(4))  # Smooth edges
        binary_A = (binary_A > 0).astype(np.uint8) * 255

        # ---------------- Label Regions ----------------
        region_labels_A = label(binary_A)
        region_props_A = regionprops(region_labels_A)

        # ---------------- Filter regions overlapping crop ----------------
        crop_start_row = h - crop_margin_h
        crop_start_col = w - crop_margin_w

        filtered_labels = []

        # Create mask for crop area
        crop_mask = np.zeros_like(region_labels_A, dtype=bool)
        crop_mask[crop_start_row:, crop_start_col:] = True

        for region in region_props_A:
            # Create mask for current region
            region_mask = (region_labels_A == region.label)
            # Skip region if overlapping with crop area
            if np.any(region_mask & crop_mask):
                continue
            filtered_labels.append(region.label)

        # Create new label image excluding filtered regions
        new_label_img = np.zeros_like(region_labels_A, dtype=np.int32)
        label_counter = 1
        for lbl in filtered_labels:
            new_label_img[region_labels_A == lbl] = label_counter
            label_counter += 1

        # Zero out crop region in original label image
        region_labels_A[crop_start_row:, crop_start_col:] = 0

        # Update to filtered labels and properties
        region_labels_A = new_label_img
        region_props_A = regionprops(region_labels_A)

        # ---------------- Compute Area Statistics ----------------
        areas = [region.area for region in region_props_A]
        median_area = np.median(areas)
        std_area = np.std(areas)
        min_area = np.min(areas)

        average = median_area + std_area  # Area threshold for splitting

        # ---------------- Plot histogram of areas ----------------
        fig, ax = plt.subplots()
        ax.hist(areas, bins=20, color='skyblue', edgecolor='black')
        hist_path_Areas = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Histogram_Areas.png")
        fig.savefig(hist_path_Areas)
        all_output_files.append(hist_path_Areas)

        # ---------------- Refine large regions using watershed ----------------
        for region in region_props_A:
            if region.area < average:
                new_label_img[region.slice][region.image] = label_counter
                label_counter += 1
            else:
                # Create mask for this large region
                region_mask = np.zeros_like(region_labels_A, dtype=np.uint8)
                region_mask[region.slice] = region.image.astype(np.uint8)

                # Compute distance transform
                distance = distance_transform_edt(region_mask)

                # Find local maxima for watershed markers
                coordinates = peak_local_max(distance, labels=region_mask, min_distance=5)
                local_maxi = np.zeros_like(distance, dtype=bool)
                local_maxi[tuple(coordinates.T)] = True
                markers = label(local_maxi)

                # Apply watershed to split region
                labels_ws = watershed(-distance, markers, mask=region_mask)

                for ws_label in np.unique(labels_ws):
                    if ws_label == 0:
                        continue
                    mask = labels_ws == ws_label
                    new_label_img[mask] = label_counter
                    label_counter += 1

        # ---------------- Update final regions ----------------
        region_labels_A = new_label_img
        region_props_A = regionprops(region_labels_A)

        # Resize binary mask if shapes do not match
        if binary_A.shape != grayA.shape:
            binary_A = resize(binary_A, grayA.shape, order=0, preserve_range=True, anti_aliasing=False)

        # ---------------- Annotate Image ----------------
        overlay_image = cv2.cvtColor((binary_A > 0).astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)

        for region in regionprops(region_labels_A):
            y, x = region.centroid
            label_id = region.label
            cv2.putText(
                overlay_image,
                str(label_id),
                (int(x), int(y)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),  # Red
                1,
                cv2.LINE_AA
            )

        # Save annotated image
        annotated_path = os.path.join(output_dir, f"{bf_file.name}_Segmented_Annotated.png")
        cv2.imwrite(annotated_path, overlay_image)
        all_output_files.append(annotated_path)

        # ---------------- Filter and generate final binary mask ----------------
        filtered_binary_A = np.zeros_like(binary_A)
        for prop in region_props_A:
            if prop.area > 0:
                min_row, min_col, max_row, max_col = prop.bbox
                filtered_binary_A[min_row:max_row, min_col:max_col] = (
                    region_labels_A[min_row:max_row, min_col:max_col] == prop.label
                )

        filtered_binary_A = (filtered_binary_A > 0).astype(np.uint8) * 255

        # ---------------- Export Area Data ----------------
        region_area_df = pd.DataFrame({
            "Region_Label": [region.label for region in region_props_A],
            "Region_Area (pixels)": [region.area for region in region_props_A],
            "Region_Area (µm²)": [r.area * (PIXEL_TO_UM ** 2) for r in region_props_A]
        })

        # Filter out regions with zero area
        region_area_df = region_area_df[region_area_df["Region_Area (µm²)"] > 0]
        total_cells = region_area_df["Region_Label"].count()
        region_area_df.loc["Total Area"] = ["", "Total Area", region_area_df["Region_Area (µm²)"].sum()]
        region_area_df.loc["Total Cells"] = ["", "Total Cells", total_cells]

        # Save to Excel
        excel_path = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Region_Area.xlsx")
        region_area_df.to_excel(excel_path, index=False)

        # ---------------- Histogram of pixel intensities ----------------
        fig, ax = plt.subplots()
        ax.hist(grayA.ravel(), bins=256, range=[0, 255])
        ax.axvline(threshold, color='red', linestyle='--')
        hist_path_A = os.path.join(output_dir, f"{os.path.splitext(bf_file.name)[0]}_Histogram_A.png")
        fig.savefig(hist_path_A)
        all_output_files.append(hist_path_A)

        # ---------------- Store Results ----------------
        st.session_state.script3_results.append({
            "bf_name": bf_file.name,
            "annotated_path": annotated_path,
            "hist_A_path": hist_path_A,
            "hist_path_Areas": hist_path_Areas,
            "excel_path": excel_path,
        })

    # ---------------- Create ZIP Archive ----------------
    zip_path_3 = os.path.join(output_dir, "All_Images_histograms.zip")
    with zipfile.ZipFile(zip_path_3, 'w') as zipf_3:
        for file_path in all_output_files:
            zipf_3.write(file_path, arcname=os.path.basename(file_path))
    st.session_state.zip_path_3 = zip_path_3
    st.success("✅ Processing complete!")

# -------------------- Display Outputs and Download Buttons --------------------

if st.session_state.script3_results:
    st.header("📦 Results")

    for result3 in st.session_state.script3_results:
        st.subheader(f"📁 {result3['bf_name']}")
        st.image(result3["annotated_path"], caption="Segmented Image")
        st.image(result3["hist_path_Areas"], caption="Areas Histogram")
        st.image(result3["hist_A_path"], caption="Pixels Intensity Histogram")

        with open(result3["excel_path"], "rb") as f3:
            st.download_button("📊 Download Dataset", f3, file_name=os.path.basename(result3["excel_path"]), key=f"download_button_{os.path.basename(result3['excel_path'])}")

    with open(st.session_state.zip_path_3, "rb") as zf_3:
        st.download_button("🗂️ Download All Images and Histograms", zf_3, file_name="All_Images_histograms.zip")


