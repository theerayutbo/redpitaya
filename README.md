# Red Pitaya Impedance Analyzer GUI

This project provides a comprehensive graphical user interface (GUI) for performing impedance analysis using the Red Pitaya STEM 125-14. The system is designed for material characterization, allowing users to measure, calibrate, compare, and analyze impedance data across a range of frequencies.

The main application is `ImpledanceAnalysor.py`, which provides a feature-rich interface for complex measurement workflows, including Eigenvalue Analysis for MPT (Magnetic Particle Testing).

![Impedance Analyser GUI](https://i.imgur.com/your-image-url.png)  <!-- Placeholder: Replace with an actual screenshot URL -->

## Core Components

- **`ImpledanceAnalysor.py`**: The main graphical user interface built with `customtkinter`. It serves as the central control panel for all measurement and analysis tasks.
- **`Background.py`**: A class-based module that encapsulates the core logic for interacting with the Red Pitaya. It handles signal generation, data acquisition (DMA), FFT calculation, and impedance measurement. This module is used by the GUI to perform measurements in a separate thread.
- **`rp_scpi.py`**: A library for communicating with the Red Pitaya using SCPI (Standard Commands for Programmable Instruments) commands over a network socket.
- **`DeepMemoryAcquisitionWithFFT3.py`**: A standalone script for simple waveform generation and data acquisition. It's primarily for demonstration and understanding the basic principles of interacting with the Red Pitaya.

## Features

The `ImpedanceAnalysor.py` GUI provides four main tabs:

### 🔴 Live Measurement
- **Sweep Measurement:** Perform frequency sweeps by specifying start frequency, end frequency, and number of points.
- **Configurable Parameters:** Set the number of averages per point for improved accuracy.
- **Measurement Types:**
    - **Metal:** For measuring metal samples. Requires specifying metal type, sample number, and measurement direction (1-16).
    - **Background (Air):** For measuring the baseline impedance in air.
    - **Calibration (Ferrite):** For measuring a ferrite core for calibration purposes.
- **Real-time Plotting:** View the real and imaginary parts of the impedance as they are being measured.
- **Automated Data Storage:** Results are automatically saved in a structured folder hierarchy under `Measurement_Data/`.

### 📊 Compare Results
- **Load and Compare:** Load multiple `summary_results.csv` files from different measurements (or entire folders) to overlay their impedance plots.
- **Filtering:** Filter the displayed data by metal type and measurement direction.
- **Plot Types:** Choose to display Real parts, Imaginary parts, or both on the comparison graph.

### 🔬 Calculation
- **Calibrated Measurement:** Automatically finds the relevant background and ferrite measurements to calculate the calibrated impedance of a metal sample.
- **Formula:** `Z_calibrated = (Z_metal - Z_background_metal) / (Z_ferrite - Z_background_ferrite)`
- **Visualization:** Plot the calibrated impedance.
- **Save Results:** Save the calculated calibrated data to a new `_CALIBRATED.csv` file, either in the source directory or a new location.

### 🧬 Eigenvalue Analysis
- **MPT Data Processing:** Designed for Magnetic Particle Testing (MPT) analysis.
- **Load Data:** Load multiple `_CALIBRATED.csv` files for a specific sample (requires at least 6 directions).
- **Eigenvalue Calculation:** Calculates the three principal eigenvalues (E1, E2, E3) of the impedance tensor.
- **Visualization:** Plot the real and imaginary parts of the eigenvalues against frequency.
- **Save Eigenvalues:** Export the calculated eigenvalue data to a `_Eigenvalues.csv` file.

## Hardware Requirements

- **Red Pitaya STEM 125-14**
- A computer to run the Python GUI.
- An Ethernet connection between the Red Pitaya and the computer.

## Software Requirements

- **Python 3.x**
- **Python Libraries:** See the `requirements.txt` file.

You can install the required Python libraries using pip. It's highly recommended to use a virtual environment.

```bash
# Create and activate a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt
```

## How to Use

1.  **Prerequisites:**
    *   Ensure all hardware is connected correctly.
    *   Make sure all software requirements are met and libraries are installed.
    *   Connect your test probe/sensor to the Red Pitaya's inputs and outputs.

2.  **Run the Application:**
    The primary way to use this project is by running the main GUI application.
    ```bash
    python ImpledanceAnalysor.py
    ```

3.  **Perform a Measurement (Example Workflow):**
    a.  Navigate to the **🔴 Live Measurement** tab.
    b.  Select the measurement type (e.g., "Metal").
    c.  If measuring a metal, fill in the "Metal Type", "Sample Number", and "Direction".
    d.  Set the sweep parameters (e.g., Freq Start: 100 Hz, Freq End: 100000 Hz, Points: 30).
    e.  Click **▶️ Start Measurement**.
    f.  A dialog will show where the data will be saved. The GUI will plot the results in real-time.
    g.  Repeat the process for background and calibration measurements as needed.

4.  **Analyze the Data:**
    a.  Go to the **🔬 Calculation** tab to calculate calibrated impedance from your raw measurements.
    b.  Use the **📊 Compare Results** tab to compare different measurements.
    c.  Use the **🧬 Eigenvalue Analysis** tab for advanced MPT analysis.

## Data Storage Structure

The application creates a `Measurement_Data` directory to store all results. The structure is organized as follows:

```
Measurement_Data/
├── background/
│   └── 20231027-143000/
│       ├── raw_freq_data/
│       │   └── ... (individual frequency measurement files)
│       └── summary_results.csv
├── calibration/
│   └── 20231027-143500/
│       └── ...
└── metal/
    └── aluminum/
        └── Sample_1/
            └── Direction_5/
                └── 20231027-144000/
                    ├── raw_freq_data/
                    │   └── ...
                    ├── summary_results.csv
                    └── aluminum_S1_D5 (14-40)_CALIBRATED.csv  (Optional, from Calculation tab)
```

## License

This project is provided for academic and research purposes. Please do not use for commercial purposes without permission.

## Contributing

Contributions are welcome. If you have suggestions for improvements, please fork the repository, create a new branch for your feature or bug fix, and submit a pull request.
