# Gemini Agent Workspace Instructions

Welcome, fellow AI! This document provides instructions for understanding and working with the Red Pitaya Impedance Analyzer project.

## Project Overview

The primary goal of this project is to provide a comprehensive tool for material analysis by measuring impedance characteristics using a Red Pitaya STEM 125-14. The system is controlled via a Python GUI (`ImpledanceAnalysor.py`) that orchestrates signal generation, data acquisition, processing, and analysis.

The workflow is designed for scientific and engineering use, enabling users to perform repeatable measurements, calibrate results against standards (like air and ferrite), and perform advanced analysis such as MPT Eigenvalue calculations.

## Codebase Architecture

The project is composed of three key Python files that work together:

1.  **`ImpledanceAnalysor.py`**
    -   **Role:** Main application entry point and Graphical User Interface (GUI).
    -   **Technology:** `customtkinter` for the UI, `matplotlib` for plotting.
    -   **Functionality:** This file defines the entire user experience. It contains the logic for all UI elements (buttons, tabs, plots, entry fields) and manages the application state. It orchestrates the entire measurement and analysis workflow by calling the `Background` class.
    -   **Key characteristic:** It is event-driven. User actions (like clicking "Start Measurement") trigger methods within the `SweepApp` class. For long-running tasks like frequency sweeps, it spawns a `MeasurementThread` to avoid freezing the GUI.
    -   **Where to modify:**
        -   To change the UI layout, look for the `create_*_tab` methods.
        -   To change how user input is handled, find the methods connected to the `command` of UI widgets (e.g., `start_measurement`).
        -   To alter how data is plotted, look for the `redraw_*_plot` or `init_plot` methods.

2.  **`Background.py`**
    -   **Role:** The core logic engine. This module acts as a bridge between the high-level GUI and the low-level hardware communication.
    -   **Technology:** `numpy` for calculations, `rp_scpi` for hardware control.
    -   **Functionality:** Encapsulated in the `Background` class, it handles the detailed steps of a measurement:
        -   Connecting to the Red Pitaya.
        -   Configuring the signal generator (`_generate_signal`).
        -   Setting up DMA acquisition parameters (`_setup_acquisition`, `_calculate_acquisition_parameters`).
        -   Triggering and acquiring data (`_acquire_data`).
        -   Processing the raw data (FFT, impedance calculation) using `numpy`.
        -   Averaging multiple measurements.
    -   **Where to modify:**
        -   To change the signal processing (e.g., use a different windowing function for the FFT), modify the `calculate_fft` or `calculate_impedance` methods.
        -   To adjust how the Red Pitaya is configured (e.g., change trigger settings), look inside `_setup_acquisition` and `_acquire_data`.
        -   To add new calculations based on the acquired data, add a new method to this class.

3.  **`rp_scpi.py`**
    -   **Role:** Low-level SCPI communication library.
    -   **Functionality:** Provides a Python class (`scpi`) that handles the socket connection to the Red Pitaya. It includes methods (`tx_txt`, `rx_txt`, `txrx_txt`) to send raw SCPI command strings and receive responses. This file abstracts the network communication details.
    -   **Where to modify:** You should rarely need to modify this file, unless the Red Pitaya firmware updates with new SCPI commands that need to be added, or if there's a fundamental change in the communication protocol.

## Standard Workflow

A typical user interaction with the program follows these steps:

1.  User runs `python ImpledanceAnalysor.py`.
2.  The `SweepApp` class initializes, creating the GUI.
3.  User configures a measurement in the "Live Measurement" tab and clicks "Start".
4.  The `start_measurement` method in `ImpledanceAnalysor.py` is called.
5.  It validates the user's input and creates a `MeasurementThread`.
6.  The `MeasurementThread` (running in the background) instantiates the `Background` class.
7.  For each frequency point in the sweep, the thread calls `Background.measure_impedance()`.
8.  Inside `measure_impedance`, the `Background` object communicates with the Red Pitaya via `rp_scpi.py` to generate a signal and acquire data.
9.  The acquired data is processed (FFT, etc.) and the impedance result is calculated.
10. The thread sends the result back to the GUI using a thread-safe callback (`queue_gui_update`).
11. The GUI's `process_gui_update` method receives the data and updates the live plot and status labels.
12. The `Background` object saves the detailed results to the appropriate folder in `Measurement_Data`.
13. Once the sweep is finished, the thread signals completion to the GUI.

## Agent Guidelines for Future Work

-   **Don't Edit `rp_scpi.py` Lightly:** This file is stable. Changes here risk breaking the fundamental connection to the hardware.
-   **Isolate Logic:**
    -   If the task involves **hardware interaction or data processing**, the changes should almost always be in **`Background.py`**.
    -   If the task involves **user interface or user workflow**, the changes belong in **`ImpledanceAnalysor.py`**.
-   **Respect Threading:** All long-running measurement tasks are offloaded to `MeasurementThread` to keep the GUI responsive. When adding new, time-consuming functions, follow this pattern. Communication from the worker thread back to the GUI **must** go through the `queue_gui_update` callback mechanism.
-   **Data Storage:** The `Measurement_Data` directory is the "database" of this application. Understand its structure before making changes to how data is saved or loaded. The `get_label_from_path` function in the GUI is key to how file paths are parsed for display.
-   **Test Standalone First:** For complex new processing algorithms, consider testing them in a separate script or by temporarily modifying `DeepMemoryAcquisitionWithFFT3.py` before integrating them into the `Background` class and the main GUI.
