# Red Pitaya STEM 125-14: Signal Generation, DMA Data Acquisition, and Impedance Analysis with FFT

This project demonstrates how to use the Red Pitaya STEM 125-14 to perform the following tasks:
- Generate sine wave signals with configurable frequency and amplitude.
- Acquire data from two channels using Direct Memory Acquisition (DMA).
- Perform Fast Fourier Transform (FFT) on the acquired signals.
- Calculate impedance, including its magnitude, phase, real, and imaginary components.
- Average results over multiple acquisition runs.
- Visualize the acquired signals and impedance measurements through plots.
- Save the calculated average impedance and other parameters to a text file.

The primary script, `DeepMemoryAcquisitionWithFFT3.py`, handles the interaction with the Red Pitaya device, data processing, and result presentation.

## Features

- **Signal Generation:** Generates sine waves with user-defined frequency and amplitude using the Red Pitaya.
- **Dual-Channel Data Acquisition:** Acquires data simultaneously from two channels of the Red Pitaya.
- **Direct Memory Acquisition (DMA):** Utilizes DMA for high-speed data transfer from the Red Pitaya.
- **FFT Analysis:** Performs Fast Fourier Transform on the acquired time-domain signals to analyze frequency components.
- **Impedance Calculation:** Calculates complex impedance, including:
    - Magnitude
    - Phase (in degrees)
    - Real part
    - Imaginary part
- **Averaging:** Averages measurements over multiple runs to improve accuracy.
- **Data Visualization:** Generates plots for:
    - Voltage signals over time for each run.
    - Current signals over time for each run.
    - Impedance magnitude and phase per run.
    - Real and imaginary parts of impedance per run.
- **Results Logging:** Saves key results (frequency, average voltage, average current, average impedance) to a text file.
- **Configurable Parameters:** Allows configuration of parameters such as Red Pitaya IP address, signal frequency, amplitude, decimation factor, and number of averaging runs.

## Hardware Requirements

- **Red Pitaya STEM 125-14:** This project is specifically designed for this Software Defined Radio (SDR) and data acquisition platform.
- **Computer:** A computer to run the Python script and connect to the Red Pitaya over a network.
- **Network Connection:** An Ethernet connection between the Red Pitaya and the computer.

## Software Requirements

- **Python 3.x:** The script is written for Python 3.
- **Python Libraries:**
    - `numpy`
    - `scipy`
    - `matplotlib`
    - `rp-scpi` (The Red Pitaya SCPI library for Python)
- **Operating System:** A compatible operating system (e.g., Linux, macOS, Windows) that can run Python and connect to the Red Pitaya.

You can install the required Python libraries using pip. It's recommended to use a virtual environment.

1.  **Create `requirements.txt`:**
    A `requirements.txt` file is included in this repository for easy installation of dependencies.

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

    If the `rp-scpi` library is not available via pip or if you need a specific version, you might need to install it directly from its source or follow instructions provided by Red Pitaya. The script uses `rp_scpi.py`, so ensure this module is accessible in your Python environment.

## How to Use

1.  **Ensure Prerequisites:**
    *   Verify that all hardware is connected correctly (Red Pitaya to network, computer to network).
    *   Make sure all software requirements are met and libraries are installed (see "Software Requirements" section).

2.  **Configure Script Parameters:**
    Open the `DeepMemoryAcquisitionWithFFT3.py` script and modify the following parameters at the beginning of the file if needed:
    *   `IP`: Set this to the IP address or hostname of your Red Pitaya device (e.g., `'rp-f05577.local'` or `'192.168.1.100'`).
    *   `wave_form`: The type of waveform to generate (default is `'sine'`).
    *   `freq`: The frequency of the generated sine wave in Hz (e.g., `500`).
    *   `ampl`: The amplitude of the generated sine wave in Volts (e.g., `0.5`).
    *   `average`: The number of times the measurement will be repeated and averaged (e.g., `3`).
    *   `DATA_SIZE`: The size of the acquisition buffer in samples.
    *   `READ_DATA_SIZE`: The number of samples to read from the buffer.
    *   `dec`: The decimation factor. The final sampling rate will be 125 MHz / `dec`.
    *   `trig_lvl`: The trigger level in Volts.

3.  **Run the Script:**
    Execute the Python script from your terminal:
    ```bash
    python DeepMemoryAcquisitionWithFFT3.py
    ```

4.  **Observe Output:**
    *   The script will print status messages to the console, including connection status, signal generation details, trigger events, acquired data information, and calculated impedance values for each run and the final averaged values.
    *   **Plots:** Matplotlib windows will appear displaying:
        *   Voltage vs. Time for each acquisition run.
        *   Current vs. Time for each acquisition run.
        *   Impedance Magnitude and Phase for each run, along with the average.
        *   Real and Imaginary parts of Impedance for each run.
    *   **Results File:** A text file will be created in a directory named `DeepMemoryAcquisitionWithFFT_results`. The filename will be based on the decimation factor and number of averages (e.g., `error_dec625_avg3.txt`). This file contains:
        *   Frequency (Hz)
        *   Average Voltage (V)
        *   Average Current (A)
        *   Average Impedance (ohm)

5.  **Troubleshooting:**
    *   **Connection Issues:** Ensure the Red Pitaya is powered on, connected to the network, and the `IP` address in the script is correct. Try pinging the Red Pitaya from your computer.
    *   **Library Errors:** Double-check that all required Python libraries are installed correctly in the environment you are using to run the script.
    *   **SCPI Errors:** Errors from the `rp_scpi` library might indicate issues with the commands being sent to the Red Pitaya or with the device's state. Consult the Red Pitaya documentation if specific SCPI errors occur.

## Script Overview

The `DeepMemoryAcquisitionWithFFT3.py` script performs several key operations:

1.  **Initialization and Configuration:**
    *   Imports necessary libraries (`time`, `matplotlib.pyplot`, `numpy`, `scipy.signal`, `tkinter`, `os`, `rp_scpi`).
    *   Sets global parameters like Red Pitaya IP, signal properties (waveform, frequency, amplitude), acquisition settings (data size, decimation), and number of averaging runs.
    *   Establishes a connection with the Red Pitaya using the `rp_scpi` library.

2.  **Signal Generation:**
    *   Resets the Red Pitaya's signal generator.
    *   Configures Channel 1 to output the specified waveform (e.g., sine wave) with the set frequency and amplitude.
    *   Enables the output of Channel 1.

3.  **Data Acquisition Loop (Repeated for `average` number of times):**
    *   **Acquisition Setup:**
        *   Resets the acquisition system.
        *   Retrieves memory region details (start address, size).
        *   Sets the decimation factor, data units (Volts).
        *   Configures trigger delay for both channels.
        *   Allocates buffer space for Channel 1 and Channel 2 in the Red Pitaya's memory.
        *   Enables DMA for both channels.
        *   Sets the trigger level and source (Channel 1 positive edge).
    *   **Triggering and Data Capture:**
        *   Starts the acquisition process.
        *   Waits for the trigger condition to be met.
        *   Waits for the DMA buffer to fill up.
        *   Stops the acquisition.
    *   **Data Retrieval:**
        *   Gets the write pointer position at the trigger location for both channels.
        *   Reads the acquired data (voltage samples) for Channel 1 and Channel 2 from the Red Pitaya's memory.
        *   Converts the raw string data into lists of floats.

4.  **Signal Processing (within the loop):**
    *   **Zero-Crossing Detection:** Identifies zero crossings in the voltage signal to extract full cycles, ensuring coherent sampling for FFT.
    *   **Impedance Calculation:**
        *   Calculates the Fast Fourier Transform (FFT) of the (full-cycle) voltage and current signals.
        *   Determines the complex impedance at the fundamental frequency.
        *   Extracts impedance magnitude, phase, real part, and imaginary part.
    *   Stores the processed voltage, current, and complex impedance for the current run.

5.  **Averaging Results (after the loop):**
    *   Calculates the average complex impedance from all runs.
    *   Derives the average magnitude, phase, real, and imaginary parts from the average complex impedance.
    *   Calculates simple averages for voltage and current magnitudes (note: phase information is critical for impedance, so complex averaging is used there).

6.  **Plotting:**
    *   Uses `matplotlib` to generate several plots:
        *   Voltage waveforms for each run.
        *   Current waveforms for each run.
        *   Impedance magnitude and phase for each run, with average values highlighted.
        *   Real and imaginary parts of impedance for each run.
    *   Displays the plots.

7.  **Saving Results:**
    *   Creates a directory named `DeepMemoryAcquisitionWithFFT_results` if it doesn't exist.
    *   Saves the configuration (frequency) and key averaged results (voltage, current, impedance) to a `.txt` file. The filename includes decimation and averaging parameters.

8.  **Cleanup:**
    *   Disables DMA on both channels of the Red Pitaya.
    *   Closes the connection to the Red Pitaya.

## License

This project is provided under a license. Please do not use for commercial purposes.

*(Note: If you intend to use a specific open-source license like MIT, GPL, Apache 2.0, etc., please replace the text above with the terms of that license or a link to it.)*

## Contributing

Contributions to this project are welcome. If you have suggestions for improvements, please feel free to:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix.
3.  Make your changes.
4.  Submit a pull request.

Please ensure your code is well-commented and, if applicable, update the README.md with any relevant changes.
