#!/usr/bin/env python3

import tkinter
from tkinter import filedialog, messagebox
import customtkinter as ctk
import os
import time
import numpy as np
from datetime import datetime
import pandas as pd
from threading import Thread, Event
import sys
import re # เพิ่ม import สำหรับ regular expression

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# --- คลาส Helper: Tooltip ---
class ToolTip(object):
    def __init__(self, widget, text):
        self.widget = widget; self.text = text; self.tip_window = None
        self.widget.bind("<Enter>", self.enter); self.widget.bind("<Leave>", self.leave)
    def enter(self, event=None): self.schedule()
    def leave(self, event=None): self.unschedule(); self.hidetip()
    def schedule(self): self.unschedule(); self.id = self.widget.after(500, self.showtip)
    def unschedule(self):
        id = getattr(self, 'id', None)
        if id: self.widget.after_cancel(id)
    def showtip(self, event=None):
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25; y += self.widget.winfo_rooty() + 20
        self.tip_window = tw = tkinter.Toplevel(self.widget); tw.wm_overrideredirect(True); tw.wm_geometry(f"+{x}+{y}")
        label = ctk.CTkLabel(tw, text=self.text, justify='left', fg_color=("#333333", "#DCE4EE"), text_color=("#DCE4EE", "#333333"), corner_radius=6, padx=8, pady=4)
        label.pack(ipadx=1)
    def hidetip(self):
        tw = self.tip_window; self.tip_window = None
        if tw: tw.destroy()

# --- คลาสสำหรับ Thread การวัด ---
class MeasurementThread(Thread):
    def __init__(self, params, app_callback):
        super().__init__(); self.params = params; self.app_callback = app_callback; self.stop_event = Event()
    def run(self):
        base_results_dir = self.params['output_path']; raw_freq_data_dir = os.path.join(base_results_dir, "raw_freq_data"); summary_filename = os.path.join(base_results_dir, "summary_results.csv")
        os.makedirs(raw_freq_data_dir, exist_ok=True); self.app_callback('log', f"สร้างโฟลเดอร์สำหรับผลลัพธ์ที่: {base_results_dir}")
        with open(summary_filename, 'w') as summary_file: summary_file.write("Timestamp,Frequency,Z_Magnitude,Z_Phase,Z_Real,Z_Imaginary,Voltage_Real,Voltage_Imaginary,Current_Real,Current_Imaginary\n")
        self.app_callback('log', f"สร้างไฟล์สรุป: {summary_filename}"); frequencies = np.logspace(np.log10(self.params['min_freq']), np.log10(self.params['max_freq']), self.params['num_points']); ts_start = datetime.now()
        for i, frequency in enumerate(frequencies):
            if self.stop_event.is_set(): self.app_callback('cancelled', {}); return
            try:
                analyzer = Background(); z, z_mag, z_phase, z_real, z_imag, v_real, v_imag, i_real, i_imag = analyzer.measure_impedance(frequency, self.params['averages'])
                analyzer.save_results(frequency, results_dir=raw_freq_data_dir, base_name=f"measurement_f_{frequency:.2f}", file_extension=".txt"); analyzer.close(); timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(summary_filename, 'a') as summary_file: summary_file.write(f"{timestamp},{frequency},{z_mag},{z_phase},{z_real},{z_imag},{v_real},{v_imag},{i_real},{i_imag}\n")
                elapsed = (datetime.now() - ts_start).total_seconds(); progress = (i + 1) / len(frequencies); eta = (elapsed / progress) - elapsed if progress > 0 else 0
                update_data = {'progress': progress, 'status': f"วัดที่ความถี่: {frequency:.1f} Hz ({i+1}/{len(frequencies)})", 'eta': eta, 'point_data': {'freq': frequency, 'z_real': z_real, 'z_imag': z_imag}}
                self.app_callback('update', update_data)
            except Exception as e: self.app_callback('error', {'error': f"เกิดข้อผิดพลาดที่ {frequency:.1f} Hz: {e}"})
        self.app_callback('finished', {'summary_path': summary_filename})
    def stop(self): self.stop_event.set()

# --- คลาสสำหรับคำนวณ MPT และ Eigenvalues ---
class MPTCalculator:
    def __init__(self):
        C0, C1, C2, C3 = (0.927050983124842272, 1.330586997335501411, 2.152934986677507057, 2.427050983124842272)
        self.H16 = np.array([[C2,C1,0],[1.5,1.5,1.5],[0,C0,C3],[-C1,0,C2],[-1.5,-1.5,1.5],[-C0,-C3,0],[0,-C2,-C1],[1.5,-1.5,-1.5],[C3,0,-C0],[C3,0,C0],[C1,0,C2],[0,-C0,C3],[0,-C2,C1],[C0,-C3,0],[C2,-C1,0],[1.5,-1.5,1.5]])
    def calculate_eigenvalues(self, calibrated_data):
        if len(calibrated_data) < 6: raise ValueError("ต้องมีข้อมูลอย่างน้อย 6 ทิศทางในการคำนวณ")
        selected_dirs = sorted(list(calibrated_data.keys())); dir_indices = [d - 1 for d in selected_dirs]
        h_selected = self.H16[dir_indices]; h_norm = h_selected / np.linalg.norm(h_selected, axis=1, keepdims=True)
        A = np.array([[h[0]**2, 2*h[0]*h[1], 2*h[0]*h[2], h[1]**2, 2*h[1]*h[2], h[2]**2] for h in h_norm])
        freqs = calibrated_data[selected_dirs[0]]['Frequency'].values; num_freqs = len(freqs)
        V = np.zeros((num_freqs, len(selected_dirs)), dtype=np.complex128)
        for i, direction in enumerate(selected_dirs):
            df = calibrated_data[direction]
            V[:, i] = df['Z_Calibrated_Real'].values + 1j * df['Z_Calibrated_Imag'].values
        eig1, eig2, eig3 = [], [], []
        for i in range(num_freqs):
            m, *_ = np.linalg.lstsq(A, V[i].reshape(-1, 1), rcond=None)
            M = np.array([[m[0,0],m[1,0],m[2,0]],[m[1,0],m[3,0],m[4,0]],[m[2,0],m[4,0],m[5,0]]], dtype=np.complex128)
            ev_sorted = sorted(np.linalg.eigvals(M), key=lambda x: x.real)
            eig1.append(ev_sorted[0]); eig2.append(ev_sorted[1]); eig3.append(ev_sorted[2])
        eig1, eig2, eig3 = np.array(eig1), np.array(eig2), np.array(eig3)
        return {'freq': freqs, 'eig1_real': eig1.real, 'eig1_imag': eig1.imag, 'eig2_real': eig2.real, 'eig2_imag': eig2.imag, 'eig3_real': eig3.real, 'eig3_imag': eig3.imag}

# --- คลาสหลักของแอปพลิเคชัน ---
class SweepApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Impedance Analyser (v3.0 - Final)"); self.geometry("1400x850"); ctk.set_appearance_mode("System"); ctk.set_default_color_theme("blue")
        self.grid_columnconfigure(0, weight=3); self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)
        self.measurement_thread = None; self.data_points = []; self.current_results_dir = None
        self.loaded_data_compare = {}; self.compare_select_all_var = tkinter.IntVar(value=0)
        self.loaded_data_calc = {}; self.calc_select_all_var = tkinter.IntVar(value=0)
        self.calc_results_cache = {}
        self.mpt_calculator = MPTCalculator()
        self.mpt_samples = {}
        self.mpt_plot_options = {}
        self.color_cycle = plt.rcParams['axes.prop_cycle'].by_key()['color']
        self.compare_plot_type_var = tkinter.StringVar(value="แสดงทั้งหมด (Both)"); self.compare_metal_filter_var = tkinter.StringVar(value="All Metals"); self.compare_direction_filter_var = tkinter.StringVar(value="All Directions")
        self.calc_plot_type_var = tkinter.StringVar(value="แสดงทั้งหมด (Both)"); self.calc_metal_filter_var = tkinter.StringVar(value="All Metals"); self.calc_direction_filter_var = tkinter.StringVar(value="All Directions")
        self.metal_types = ["Aluminum", "Copper", "Brass"]
        self.create_main_layout()

    def create_main_layout(self):
        self.tab_view = ctk.CTkTabview(self, corner_radius=10); self.tab_view.grid(row=0, column=0, padx=10, pady=10, sticky="nswe")
        self.live_tab = self.tab_view.add("🔴 Live Measurement")
        self.compare_tab = self.tab_view.add("📊 Compare Results")
        self.calc_tab = self.tab_view.add("🔬 Calculation")
        self.mpt_tab = self.tab_view.add("🧬 Eigenvalue Analysis")
        self.create_log_sidebar()
        self.create_live_measurement_tab()
        self.create_comparison_tab()
        self.create_calculation_tab()
        self.create_mpt_tab()

    def create_log_sidebar(self):
        log_frame = ctk.CTkFrame(self, corner_radius=10); log_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nswe"); log_frame.grid_rowconfigure(1, weight=1); log_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_frame, text="Log การทำงาน", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.log_textbox = ctk.CTkTextbox(log_frame, state="disabled", wrap="word", corner_radius=10); self.log_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nswe")
        self.log("โปรแกรมพร้อมทำงาน...")

    def _create_matplotlib_toolbar(self, canvas, master_frame):
        toolbar_frame = ctk.CTkFrame(master_frame, fg_color="transparent"); toolbar_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(0, 5))
        toolbar = NavigationToolbar2Tk(canvas, toolbar_frame, pack_toolbar=False); toolbar.update()
        bg_color = master_frame.cget("fg_color")[1]; text_color = "#DCE4EE" if ctk.get_appearance_mode() == "Dark" else "#333333"
        toolbar.config(background=bg_color); toolbar._message_label.config(background=bg_color, foreground=text_color)
        for button in toolbar.winfo_children(): button.config(background=bg_color)
        toolbar.pack(side="left")

    def create_live_measurement_tab(self):
        self.live_tab.grid_columnconfigure(1, weight=1); self.live_tab.grid_rowconfigure(0, weight=1)
        self.create_setup_frame(master=self.live_tab); self.create_monitoring_frame(master=self.live_tab)

    def create_setup_frame(self, master):
        self.setup_frame = ctk.CTkFrame(master, width=320, corner_radius=10); self.setup_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nswe"); self.setup_frame.grid_propagate(False); self.setup_frame.grid_rowconfigure(0, weight=1)
        scrollable_params_frame = ctk.CTkScrollableFrame(self.setup_frame, fg_color="transparent"); scrollable_params_frame.grid(row=0, column=0, sticky="nsew", padx=5)
        ctk.CTkLabel(scrollable_params_frame, text="1. ประเภทการวัด", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5), padx=10, anchor="w")
        self.measurement_type = tkinter.StringVar(value="background")
        ctk.CTkRadioButton(scrollable_params_frame, text="Metal (โลหะ)", variable=self.measurement_type, value="metal", command=self.toggle_metal_widgets).pack(pady=5, padx=10, anchor="w")
        ctk.CTkRadioButton(scrollable_params_frame, text="Background (อากาศ)", variable=self.measurement_type, value="background", command=self.toggle_metal_widgets).pack(pady=5, padx=10, anchor="w")
        ctk.CTkRadioButton(scrollable_params_frame, text="Calibration (Ferrite)", variable=self.measurement_type, value="calibration", command=self.toggle_metal_widgets).pack(pady=(5, 15), padx=10, anchor="w")
        self.metal_frame = ctk.CTkFrame(scrollable_params_frame, fg_color="transparent"); self.metal_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(self.metal_frame, text="2. รายละเอียดชิ้นงาน", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(self.metal_frame, text="ชนิดโลหะ:").pack(anchor="w", pady=(5,0)); self.metal_type_combo = ctk.CTkComboBox(self.metal_frame, values=[m.lower() for m in self.metal_types]); self.metal_type_combo.pack(fill="x")
        ctk.CTkLabel(self.metal_frame, text="หมายเลขชิ้นงาน:").pack(anchor="w", pady=(5,0)); self.sample_num_entry = ctk.CTkEntry(self.metal_frame, placeholder_text="เช่น 1, 2, 3..."); self.sample_num_entry.pack(fill="x")
        ctk.CTkLabel(self.metal_frame, text="ทิศทางการวัด (1-16):").pack(anchor="w", pady=(5,0)); self.direction_entry = ctk.CTkEntry(self.metal_frame, placeholder_text="เช่น 5, 12..."); self.direction_entry.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(scrollable_params_frame, text="3. พารามิเตอร์การ Sweep", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5, padx=10, anchor="w")
        ctk.CTkLabel(scrollable_params_frame, text="ความถี่เริ่มต้น (Hz):").pack(anchor="w", padx=10); self.min_freq_entry = ctk.CTkEntry(scrollable_params_frame, placeholder_text="เช่น 100"); self.min_freq_entry.insert(0, "100"); self.min_freq_entry.pack(fill="x", padx=10)
        ctk.CTkLabel(scrollable_params_frame, text="ความถี่สิ้นสุด (Hz):").pack(anchor="w", padx=10, pady=(5,0)); self.max_freq_entry = ctk.CTkEntry(scrollable_params_frame, placeholder_text="เช่น 100000"); self.max_freq_entry.insert(0, "100000"); self.max_freq_entry.pack(fill="x", padx=10)
        ctk.CTkLabel(scrollable_params_frame, text="จำนวนจุดวัด:").pack(anchor="w", padx=10, pady=(5,0)); self.num_points_entry = ctk.CTkEntry(scrollable_params_frame, placeholder_text="เช่น 30"); self.num_points_entry.insert(0, "30"); self.num_points_entry.pack(fill="x", padx=10)
        ctk.CTkLabel(scrollable_params_frame, text="จำนวนครั้งเฉลี่ยต่อจุด:").pack(anchor="w", padx=10, pady=(5,0)); self.averages_entry = ctk.CTkEntry(scrollable_params_frame, placeholder_text="เช่น 5"); self.averages_entry.insert(0, "5"); self.averages_entry.pack(fill="x", padx=10, pady=(0, 15))
        control_frame = ctk.CTkFrame(self.setup_frame); control_frame.grid(row=1, column=0, sticky="sew", padx=10, pady=10); control_frame.grid_columnconfigure((0,1), weight=1)
        self.start_button = ctk.CTkButton(control_frame, text="▶️ เริ่มการวัด", command=self.start_measurement, font=ctk.CTkFont(size=14, weight="bold")); self.start_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.stop_button = ctk.CTkButton(control_frame, text="⏹️ ยกเลิก", command=self.stop_measurement, state="disabled", fg_color="tomato"); self.stop_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.toggle_metal_widgets()

    def create_monitoring_frame(self, master):
        self.monitoring_frame = ctk.CTkFrame(master, corner_radius=10); self.monitoring_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nswe"); self.monitoring_frame.grid_rowconfigure(2, weight=1); self.monitoring_frame.grid_columnconfigure(0, weight=1)
        status_frame = ctk.CTkFrame(self.monitoring_frame, fg_color="transparent"); status_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew"); status_frame.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(status_frame, text="สถานะ: พร้อมทำงาน", anchor="w", font=ctk.CTkFont(size=14)); self.status_label.grid(row=0, column=0, sticky="ew")
        self.eta_label = ctk.CTkLabel(status_frame, text="ETA: --:--:--", anchor="e", font=ctk.CTkFont(size=14)); self.eta_label.grid(row=0, column=1, sticky="e")
        self.progress_bar = ctk.CTkProgressBar(status_frame, orientation="horizontal"); self.progress_bar.set(0); self.progress_bar.grid(row=1, column=0, columnspan=2, pady=(5,10), sticky="ew")
        self.save_graph_button = ctk.CTkButton(status_frame, text="💾 บันทึกกราฟ", command=self.save_graph, state="disabled"); self.save_graph_button.grid(row=2, column=0, columnspan=2, pady=0, sticky="ew")
        self.fig_live = Figure(figsize=(5, 4), dpi=100); self.ax_live = self.fig_live.add_subplot(111); self.canvas_live = FigureCanvasTkAgg(self.fig_live, master=self.monitoring_frame)
        self.canvas_live.get_tk_widget().grid(row=2, column=0, padx=10, pady=10, sticky="nswe"); self._create_matplotlib_toolbar(self.canvas_live, self.monitoring_frame); self.init_plot(self.fig_live, self.ax_live, self.canvas_live, "Live Impedance")
    
    def create_comparison_tab(self):
        self.compare_tab.grid_columnconfigure(1, weight=1); self.compare_tab.grid_rowconfigure(0, weight=1)
        compare_control_frame = ctk.CTkFrame(self.compare_tab, width=320, corner_radius=10); compare_control_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nswe"); compare_control_frame.grid_propagate(False); compare_control_frame.grid_rowconfigure(3, weight=1); compare_control_frame.grid_columnconfigure(0, weight=1)
        load_button_frame = ctk.CTkFrame(compare_control_frame, fg_color="transparent"); load_button_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew"); load_button_frame.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(load_button_frame, text="📂 Load Folder", command=self.load_compare_folder).grid(row=0, column=0, padx=5, sticky="ew")
        ctk.CTkButton(load_button_frame, text="📄 Load Files", command=self.load_compare_files).grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(load_button_frame, text="🗑️ Remove Selected", fg_color="tomato", command=self._remove_selected_compare_items).grid(row=0, column=2, padx=5, sticky="ew")
        filter_frame = ctk.CTkFrame(compare_control_frame, fg_color="transparent"); filter_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew"); filter_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(filter_frame, text="Filter by Type:").grid(row=0, column=0, padx=(0, 5), sticky="w")
        ctk.CTkOptionMenu(filter_frame, variable=self.compare_plot_type_var, values=["แสดงทั้งหมด (Both)", "เฉพาะค่า Real (Real Only)", "เฉพาะค่า Imaginary (Imag Only)"], command=self._apply_compare_filters).grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(filter_frame, text="กรองตามชนิดโลหะ:").grid(row=1, column=0, padx=(0, 5), pady=(5, 0), sticky="w")
        ctk.CTkOptionMenu(filter_frame, variable=self.compare_metal_filter_var, values=["All Metals"] + self.metal_types, command=self._apply_compare_filters).grid(row=1, column=1, pady=(5, 0), sticky="ew")
        ctk.CTkLabel(filter_frame, text="Filter by Direction:").grid(row=2, column=0, padx=(0, 5), pady=(5, 0), sticky="w")
        directions = ["All Directions"] + [f"D{i}" for i in range(1, 17)]; ctk.CTkOptionMenu(filter_frame, variable=self.compare_direction_filter_var, values=directions, command=self._apply_compare_filters).grid(row=2, column=1, pady=(5, 0), sticky="ew")
        ctk.CTkCheckBox(compare_control_frame, text="Select All / Unselect All", variable=self.compare_select_all_var, command=self.toggle_all_compare).grid(row=2, column=0, padx=15, pady=10, sticky="w")
        self.compare_list_frame = ctk.CTkScrollableFrame(compare_control_frame, label_text="Loaded Datasets"); self.compare_list_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nswe")
        compare_graph_frame = ctk.CTkFrame(self.compare_tab, corner_radius=10); compare_graph_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nswe"); compare_graph_frame.grid_rowconfigure(1, weight=1); compare_graph_frame.grid_columnconfigure(0, weight=1)
        self.fig_compare = Figure(figsize=(5, 4), dpi=100); self.ax_compare = self.fig_compare.add_subplot(111); self.canvas_compare = FigureCanvasTkAgg(self.fig_compare, master=compare_graph_frame)
        self.canvas_compare.get_tk_widget().grid(row=1, column=0, padx=10, pady=10, sticky="nswe"); self._create_matplotlib_toolbar(self.canvas_compare, compare_graph_frame); self.init_plot(self.fig_compare, self.ax_compare, self.canvas_compare, "Comparison Plot")
        
    def create_calculation_tab(self):
        self.calc_tab.grid_columnconfigure(1, weight=1); self.calc_tab.grid_rowconfigure(0, weight=1)
        calc_control_frame = ctk.CTkFrame(self.calc_tab, width=320, corner_radius=10); calc_control_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nswe"); calc_control_frame.grid_propagate(False); calc_control_frame.grid_rowconfigure(3, weight=1); calc_control_frame.grid_columnconfigure(0, weight=1)
        load_button_frame = ctk.CTkFrame(calc_control_frame, fg_color="transparent"); load_button_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew"); load_button_frame.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(load_button_frame, text="📂 Load Folder", command=self.load_calc_folder).grid(row=0, column=0, padx=5, sticky="ew")
        ctk.CTkButton(load_button_frame, text="📄 Load File", command=self.load_calc_file).grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(load_button_frame, text="🗑️ Remove Selected", fg_color="tomato", command=self._remove_selected_calc_items).grid(row=0, column=2, padx=5, sticky="ew")
        filter_frame_calc = ctk.CTkFrame(calc_control_frame, fg_color="transparent"); filter_frame_calc.grid(row=1, column=0, padx=10, pady=5, sticky="ew"); filter_frame_calc.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(filter_frame_calc, text="Filter by Type:").grid(row=0, column=0, padx=(0, 5), sticky="w")
        ctk.CTkOptionMenu(filter_frame_calc, variable=self.calc_plot_type_var, values=["แสดงทั้งหมด (Both)", "เฉพาะค่า Real (Real Only)", "เฉพาะค่า Imaginary (Imag Only)"], command=self._apply_calc_filters).grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(filter_frame_calc, text="กรองตามชนิดโลหะ:").grid(row=1, column=0, padx=(0, 5), pady=(5, 0), sticky="w")
        ctk.CTkOptionMenu(filter_frame_calc, variable=self.calc_metal_filter_var, values=["All Metals"] + self.metal_types, command=self._apply_calc_filters).grid(row=1, column=1, pady=(5, 0), sticky="ew")
        ctk.CTkLabel(filter_frame_calc, text="Filter by Direction:").grid(row=2, column=0, padx=(0, 5), pady=(5, 0), sticky="w")
        directions = ["All Directions"] + [f"D{i}" for i in range(1, 17)]; ctk.CTkOptionMenu(filter_frame_calc, variable=self.calc_direction_filter_var, values=directions, command=self._apply_calc_filters).grid(row=2, column=1, pady=(5, 0), sticky="ew")
        ctk.CTkCheckBox(calc_control_frame, text="Select All / Unselect All", variable=self.calc_select_all_var, command=self.toggle_all_calc).grid(row=2, column=0, padx=15, pady=10, sticky="w")
        self.calc_list_frame = ctk.CTkScrollableFrame(calc_control_frame, label_text="Select Metal Measurement(s) to Calculate"); self.calc_list_frame.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="nswe")
        output_frame = ctk.CTkFrame(calc_control_frame); output_frame.grid(row=4, column=0, padx=10, pady=10, sticky="ew"); output_frame.grid_columnconfigure(0, weight=1)
        self.associated_files_frame = ctk.CTkFrame(output_frame); self.associated_files_frame.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(self.associated_files_frame, text="Auto-Detected Files (for last selected)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=5, pady=(5, 10))
        ctk.CTkLabel(self.associated_files_frame, text="Background for Metal:").pack(anchor="w", padx=5); self.bg_for_metal_label = ctk.CTkLabel(self.associated_files_frame, text="N/A", text_color="gray", wraplength=280); self.bg_for_metal_label.pack(anchor="w", padx=5, pady=(0, 5))
        ctk.CTkLabel(self.associated_files_frame, text="Ferrite for Calibration:").pack(anchor="w", padx=5); self.ferrite_label = ctk.CTkLabel(self.associated_files_frame, text="N/A", text_color="gray", wraplength=280); self.ferrite_label.pack(anchor="w", padx=5, pady=(0, 5))
        ctk.CTkLabel(self.associated_files_frame, text="Background for Ferrite:").pack(anchor="w", padx=5); self.bg_for_ferrite_label = ctk.CTkLabel(self.associated_files_frame, text="N/A", text_color="gray", wraplength=280); self.bg_for_ferrite_label.pack(anchor="w", padx=5, pady=(0, 5))
        save_button_frame = ctk.CTkFrame(output_frame); save_button_frame.grid(row=1, column=0, padx=0, pady=10, sticky="ew"); save_button_frame.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(save_button_frame, text="💾 Save to Source", command=self.save_calibrated_to_source).grid(row=0, column=0, padx=5, sticky="ew")
        ctk.CTkButton(save_button_frame, text="💾 Save to New...", command=self.save_calibrated_to_new).grid(row=0, column=1, padx=5, sticky="ew")
        calc_graph_frame = ctk.CTkFrame(self.calc_tab, corner_radius=10); calc_graph_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nswe"); calc_graph_frame.grid_rowconfigure(1, weight=1); calc_graph_frame.grid_columnconfigure(0, weight=1)
        self.fig_calc = Figure(figsize=(5, 4), dpi=100); self.ax_calc = self.fig_calc.add_subplot(111); self.canvas_calc = FigureCanvasTkAgg(self.fig_calc, master=calc_graph_frame)
        self.canvas_calc.get_tk_widget().grid(row=1, column=0, padx=10, pady=10, sticky="nswe"); self._create_matplotlib_toolbar(self.canvas_calc, calc_graph_frame); self.init_plot(self.fig_calc, self.ax_calc, self.canvas_calc, "Calculation Result")

    # --- START: Eigenvalue (MPT) Tab Functions ---
    def create_mpt_tab(self):
        """สร้าง UI ทั้งหมดสำหรับแท็บ Eigenvalue Analysis (เวอร์ชันปรับ Layout ขยายกราฟ)"""
        self.mpt_samples = {}
        self.mpt_loaded_csvs = {}
        self.mpt_plot_options = {'show_type': tkinter.StringVar(value="แสดงทั้งหมด"), 'show_e1': tkinter.IntVar(value=1), 'show_e2': tkinter.IntVar(value=1), 'show_e3': tkinter.IntVar(value=1), 'show_orig': tkinter.IntVar(value=1), 'metal_filter': tkinter.StringVar(value="All Metals")}
        
        # --- ส่วนที่แก้ไข: ปรับการตั้งค่า Grid หลักของแท็บ ---
        self.mpt_tab.grid_columnconfigure(0, weight=1) # ส่วนควบคุม
        self.mpt_tab.grid_columnconfigure(1, weight=2) # ส่วนกราฟ
        self.mpt_tab.grid_rowconfigure(0, weight=1)    # ให้แถวที่ 0 (แถวเดียว) ขยายเต็มความสูง
        
        # --- Frame ควบคุมหลักด้านซ้าย ---
        mpt_control_frame = ctk.CTkFrame(self.mpt_tab, corner_radius=10, width=380) # เพิ่มความกว้างเล็กน้อย
        # แก้ไข: เอา rowspan ออก และใช้ sticky="nswe" เพื่อให้ยืดเต็ม
        mpt_control_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nswe")
        mpt_control_frame.grid_propagate(False)
        mpt_control_frame.grid_rowconfigure(1, weight=1) # ให้ลิสต์รายการขยายได้
        mpt_control_frame.grid_columnconfigure(0, weight=1)

        # --- ส่วนปุ่มควบคุมด้านบน (2x2) ---
        top_button_frame = ctk.CTkFrame(mpt_control_frame, fg_color="transparent")
        top_button_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        top_button_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(top_button_frame, text="โหลดโฟลเดอร์", command=self.load_mpt_samples_folder).grid(row=0, column=0, sticky="ew", padx=(0,5), pady=(0,5))
        ctk.CTkButton(top_button_frame, text="เปิด CSV", command=self.load_eigenvalue_csv_files).grid(row=0, column=1, sticky="ew", padx=(5,0), pady=(0,5))
        self.mpt_calc_button = ctk.CTkButton(top_button_frame, text="คำนวณ", command=self.calculate_mpt, state="disabled")
        self.mpt_calc_button.grid(row=1, column=0, sticky="ew", padx=(0,5))
        self.mpt_remove_button = ctk.CTkButton(top_button_frame, text="ลบรายการที่เลือก", fg_color="tomato", command=self.remove_selected_mpt_items)
        self.mpt_remove_button.grid(row=1, column=1, sticky="ew", padx=(5,0))
        
        # --- ส่วนแสดงรายการ ---
        self.mpt_samples_list_frame = ctk.CTkScrollableFrame(mpt_control_frame, label_text="เลือกข้อมูลสำหรับแสดงผล")
        self.mpt_samples_list_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        # --- ส่วนตัวเลือกด้านล่าง ---
        option_frame = ctk.CTkFrame(mpt_control_frame)
        option_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        # โค้ดส่วนที่เหลือของ option_frame คงเดิม...
        option_frame.grid_columnconfigure((0, 1), weight=1)
        display_options_frame = ctk.CTkFrame(option_frame, fg_color="transparent")
        display_options_frame.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        display_options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(display_options_frame, text="ตัวเลือกการแสดงผล:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0,5))
        ctk.CTkLabel(display_options_frame, text="กรองโลหะ:").grid(row=1, column=0, sticky="w", padx=5)
        self.mpt_metal_filter_menu = ctk.CTkOptionMenu(display_options_frame, variable=self.mpt_plot_options['metal_filter'], values=["All Metals"], command=self.redraw_mpt_plot)
        self.mpt_metal_filter_menu.grid(row=1, column=1, sticky="ew", pady=(0,5))
        ctk.CTkLabel(display_options_frame, text="แสดงค่า:").grid(row=2, column=0, sticky="w", padx=5)
        ctk.CTkOptionMenu(display_options_frame, variable=self.mpt_plot_options['show_type'], values=["แสดงทั้งหมด", "เฉพาะค่า Real", "เฉพาะค่า Imaginary"], command=self.redraw_mpt_plot).grid(row=2, column=1, sticky="ew", pady=(0,5))
        checkbox_frame = ctk.CTkFrame(display_options_frame, fg_color="transparent")
        checkbox_frame.grid(row=3, column=0, columnspan=2, pady=5)
        ctk.CTkCheckBox(checkbox_frame, text="E1", variable=self.mpt_plot_options['show_e1'], command=self.redraw_mpt_plot).pack(side="left", expand=True)
        ctk.CTkCheckBox(checkbox_frame, text="E2", variable=self.mpt_plot_options['show_e2'], command=self.redraw_mpt_plot).pack(side="left", expand=True)
        ctk.CTkCheckBox(checkbox_frame, text="E3", variable=self.mpt_plot_options['show_e3'], command=self.redraw_mpt_plot).pack(side="left", expand=True)
        ctk.CTkCheckBox(checkbox_frame, text="Original", variable=self.mpt_plot_options['show_orig'], command=self.redraw_mpt_plot).pack(side="left", expand=True)
        export_frame = ctk.CTkFrame(option_frame)
        export_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        export_frame.grid_columnconfigure((0,1), weight=1)
        ctk.CTkLabel(export_frame, text="ส่งออกผลลัพธ์:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(0,5))
        self.mpt_save_source_button = ctk.CTkButton(export_frame, text="Save to Source", command=lambda: self.save_mpt_results(to_source=True), state="disabled")
        self.mpt_save_source_button.grid(row=1, column=0, padx=(5,2), pady=5)
        self.mpt_save_new_button = ctk.CTkButton(export_frame, text="Save to New...", command=lambda: self.save_mpt_results(to_source=False), state="disabled")
        self.mpt_save_new_button.grid(row=1, column=1, padx=(2,5), pady=5)
        self.mpt_save_graph_button = ctk.CTkButton(export_frame, text="บันทึกกราฟ...", command=self.save_mpt_graph, state="disabled")
        self.mpt_save_graph_button.grid(row=2, column=0, columnspan=2, padx=5, pady=(5,5), sticky="ew")

        # --- Frame กราฟด้านขวา ---
        mpt_graph_frame = ctk.CTkFrame(self.mpt_tab, corner_radius=10)
        # แก้ไข: เอา rowspan ออก และใช้ sticky="nswe" เพื่อให้ยืดเต็ม
        mpt_graph_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nswe")
        mpt_graph_frame.grid_rowconfigure(1, weight=1); mpt_graph_frame.grid_columnconfigure(0, weight=1)
        self.fig_mpt = Figure(figsize=(5, 4), dpi=100); self.ax_mpt = self.fig_mpt.add_subplot(111); self.canvas_mpt = FigureCanvasTkAgg(self.fig_mpt, master=mpt_graph_frame)
        self.canvas_mpt.get_tk_widget().grid(row=1, column=0, padx=10, pady=10, sticky="nswe")
        self._create_matplotlib_toolbar(self.canvas_mpt, mpt_graph_frame)
        self.init_plot(self.fig_mpt, self.ax_mpt, self.canvas_mpt, "Eigenvalue Analysis")

    def load_mpt_samples_folder(self):
        self.log("กำลังเปิดหน้าต่างเลือกโฟลเดอร์..."); initial_dir = os.path.join("Measurement_Data", "metal") if os.path.isdir(os.path.join("Measurement_Data", "metal")) else "."
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์โลหะ (เช่น aluminium) หรือโฟลเดอร์ชิ้นงาน (เช่น Sample_24)", initialdir=initial_dir)
        if not folder: self.log("ยกเลิกการเลือกโฟลเดอร์"); return
        
        samples_to_process = []
        if os.path.basename(folder).lower().startswith("sample_"):
            samples_to_process.append(folder); metal_name = os.path.basename(os.path.dirname(folder)).capitalize()
        else:
            metal_name = os.path.basename(folder).capitalize()
            for item in os.listdir(folder):
                item_path = os.path.join(folder, item)
                if os.path.isdir(item_path) and item.lower().startswith("sample_"): samples_to_process.append(item_path)
        
        for item_path in samples_to_process:
            sample_name = f"{metal_name}_{os.path.basename(item_path)}"
            if sample_name in self.mpt_samples: continue # ข้ามถ้ามีอยู่แล้ว
            found_directions = {int(m.group(1)): os.path.join(r, f) for r, _, fs in os.walk(item_path) for f in fs if (m := re.search(r"Direction_(\d+)", os.path.join(r, f))) and f.endswith("_CALIBRATED.csv")}
            if not found_directions: self.log(f"ข้าม {sample_name}: ไม่พบไฟล์ _CALIBRATED.csv"); continue

            sample_frame = ctk.CTkFrame(self.mpt_samples_list_frame); sample_frame.pack(fill="x", pady=5, padx=5)
            self.mpt_samples[sample_name] = {'path': item_path, 'directions': {}, 'widgets': {'frame': sample_frame}, 'results': None}
            var = tkinter.IntVar(value=0)
            cb_sample = ctk.CTkCheckBox(sample_frame, text=sample_name, variable=var, font=ctk.CTkFont(weight="bold"), command=lambda name=sample_name: self._toggle_directions_for_sample(name)); cb_sample.pack(anchor="w", padx=5, pady=5)
            self.mpt_samples[sample_name]['widgets']['sample_var'] = var
            dir_frame = ctk.CTkFrame(sample_frame, fg_color="transparent"); dir_frame.pack(fill="x", padx=(25, 5))
            row, col = 0, 0
            for dir_num in sorted(found_directions.keys()):
                dir_var = tkinter.IntVar(value=0); cb_dir = ctk.CTkCheckBox(dir_frame, text=f"D{dir_num}", variable=dir_var); cb_dir.grid(row=row, column=col, padx=3, pady=2, sticky="w")
                self.mpt_samples[sample_name]['directions'][dir_num] = {'path': found_directions[dir_num], 'var': dir_var}; col += 1
                if col >= 3: col=0; row+=1

        self.log(f"พบ {len(self.mpt_samples)} ชิ้นงานทั้งหมด");
        if not samples_to_process and not self.mpt_samples: messagebox.showinfo("ไม่พบชิ้นงาน", "ไม่พบโฟลเดอร์ Sample หรือไฟล์ _CALIBRATED.csv ในตำแหน่งที่เลือก")
        self.mpt_calc_button.configure(state="normal" if self.mpt_samples else "disabled")

    def load_eigenvalue_csv_files(self):
        self.log("กำลังเปิดหน้าต่างเพื่อเลือกไฟล์ Eigenvalue CSV...")
        if not hasattr(self, 'mpt_loaded_csvs'): self.mpt_loaded_csvs = {}
        filepaths = filedialog.askopenfilenames(title="เลือกไฟล์ Eigenvalue CSV", filetypes=[("CSV Files", "*.csv")])
        if not filepaths: self.log("ยกเลิกการเลือกไฟล์"); return
        
        loaded_count = 0
        for path in filepaths:
            if path in self.mpt_loaded_csvs: self.log(f"ข้ามไฟล์ที่โหลดแล้ว: {os.path.basename(path)}"); continue
            try:
                df = pd.read_csv(path)
                required_cols = ['Frequency', 'Eig1_Real', 'Eig1_Imag', 'Eig2_Real', 'Eig2_Imag', 'Eig3_Real', 'Eig3_Imag']
                if not all(col in df.columns for col in required_cols): self.log(f"ไฟล์ {os.path.basename(path)} ไม่มีคอลัมน์ที่ถูกต้อง"); continue
                
                label = os.path.basename(path).replace("_Eigenvalues.csv", ""); var = tkinter.IntVar(value=1)
                cb = ctk.CTkCheckBox(self.mpt_samples_list_frame, text=f"📄 {label}", variable=var, command=self.redraw_mpt_plot)
                cb.pack(anchor="w", padx=5, pady=2)
                # *** เก็บ reference ของ checkbox ไว้ ***
                self.mpt_loaded_csvs[path] = {'label': label, 'df': df, 'var': var, 'widget': cb}
                loaded_count += 1
            except Exception as e: self.log(f"ไม่สามารถโหลดไฟล์ {os.path.basename(path)}: {e}")
        
        if loaded_count > 0: self.log(f"โหลดไฟล์ CSV สำเร็จ {loaded_count} ไฟล์"); self.redraw_mpt_plot()

    def _toggle_directions_for_sample(self, sample_name):
        """Toggles all direction checkboxes based on the main sample checkbox state."""
        if sample_name in self.mpt_samples:
            sample_data = self.mpt_samples[sample_name]
            # ดึงสถานะปัจจุบันของ Checkbox หลัก (0 หรือ 1)
            new_state = sample_data['widgets']['sample_var'].get()
            
            # สั่งให้ Checkbox ของทิศทางทั้งหมดเปลี่ยนสถานะตาม
            for dir_data in sample_data['directions'].values():
                dir_data['var'].set(new_state)

    def remove_selected_mpt_items(self):
        """ลบรายการที่เลือก (ทั้ง Sample และ CSV) ออกจากลิสต์และ Cache"""
        samples_to_remove = [name for name, data in self.mpt_samples.items() if data['widgets']['sample_var'].get() == 1]
        csvs_to_remove = [path for path, data in self.mpt_loaded_csvs.items() if data['var'].get() == 1]

        if not samples_to_remove and not csvs_to_remove:
            messagebox.showinfo("ไม่มีรายการที่เลือก", "กรุณาเลือกรายการที่ต้องการลบ")
            return

        # ลบ Samples
        for name in samples_to_remove:
            self.mpt_samples[name]['widgets']['frame'].destroy()
            del self.mpt_samples[name]
        
        # ลบ CSVs
        for path in csvs_to_remove:
            self.mpt_loaded_csvs[path]['widget'].destroy()
            del self.mpt_loaded_csvs[path]
        
        self.log(f"ลบ Samples {len(samples_to_remove)} รายการ และ CSVs {len(csvs_to_remove)} รายการ")
        self._update_mpt_metal_filter_options() # <<< เพิ่มตรงนี้
        self.redraw_mpt_plot()

    def _update_mpt_metal_filter_options(self):
        """อัปเดตตัวเลือกใน Dropdown ของ metal filter"""
        metals = set()
        for name in self.mpt_samples.keys():
            metals.add(name.split('_')[0])
        for data in self.mpt_loaded_csvs.values():
            metals.add(data['label'].split('_')[0])
        
        options = ["All Metals"] + sorted(list(metals))
        self.mpt_metal_filter_menu.configure(values=options)

        # ถ้าตัวเลือกเดิมไม่มีอยู่แล้ว ให้กลับไปที่ 'All Metals'
        if self.mpt_plot_options['metal_filter'].get() not in options:
            self.mpt_plot_options['metal_filter'].set("All Metals")

    def calculate_mpt(self):
        self.log("เริ่มการคำนวณ Eigenvalues..."); calculated_count = 0
        for sample_name, sample_data in self.mpt_samples.items():
            if not sample_data['widgets']['sample_var'].get(): sample_data['results'] = None; continue
            calibrated_data, original_data_for_plot = {}, {}
            for dir_num, dir_data in sample_data['directions'].items():
                if dir_data['var'].get() == 1:
                    df = pd.read_csv(dir_data['path']); calibrated_data[dir_num] = df; original_data_for_plot[dir_num] = df
            if len(calibrated_data) < 6: self.log(f"ข้าม {sample_name}: เลือกทิศทางไม่ถึง 6"); sample_data['results'] = None; continue
            try:
                self.log(f"กำลังคำนวณ {sample_name}..."); results = self.mpt_calculator.calculate_eigenvalues(calibrated_data)
                results['original_data'] = original_data_for_plot; sample_data['results'] = results
                calculated_count += 1; self.log(f"คำนวณ {sample_name} สำเร็จ")
            except Exception as e: self.log(f"คำนวณ {sample_name} ล้มเหลว: {e}"); sample_data['results'] = None
        self.log(f"การคำนวณเสร็จสิ้น ({calculated_count} ชิ้นงาน)"); self.redraw_mpt_plot()
        save_state = "normal" if calculated_count > 0 else "disabled"
        self.mpt_save_source_button.configure(state=save_state); self.mpt_save_new_button.configure(state=save_state); self.mpt_save_graph_button.configure(state=save_state)
        
    def redraw_mpt_plot(self, *args):
        self.init_plot(self.fig_mpt, self.ax_mpt, self.canvas_mpt, "Eigenvalue Analysis")
        self.ax_mpt.set_ylabel("Value")

        # ดึงค่าจาก Filter ทั้งหมด
        metal_filter = self.mpt_plot_options['metal_filter'].get()
        show_type = self.mpt_plot_options['show_type'].get()
        show_e1, show_e2, show_e3, show_orig = self.mpt_plot_options['show_e1'].get(), self.mpt_plot_options['show_e2'].get(), self.mpt_plot_options['show_e3'].get(), self.mpt_plot_options['show_orig'].get()
        
        color_idx, plotted_something = 0, False

        # พล็อตข้อมูลจากการคำนวณสด
        for sample_name, sample_data in self.mpt_samples.items():
            # *** เพิ่มเงื่อนไข Filter โลหะ ***
            if metal_filter != "All Metals" and not sample_name.startswith(metal_filter):
                continue

            if sample_data.get('results'):
                plotted_something = True
                # ... (โค้ดพล็อตส่วนที่เหลือเหมือนเดิม) ...
                results = sample_data['results']; freq = results['freq']; sample_label_short = sample_name.split('_')[-1].replace('Sample', 'S')
                if show_orig and 'original_data' in results:
                    for df in results['original_data'].values():
                        if show_type != "เฉพาะค่า Imaginary": self.ax_mpt.plot(df['Frequency'], df['Z_Calibrated_Real'], color=self.color_cycle[color_idx % len(self.color_cycle)], linestyle='--', linewidth=0.8, alpha=0.5)
                        if show_type != "เฉพาะค่า Real": self.ax_mpt.plot(df['Frequency'], df['Z_Calibrated_Imag'], color=self.color_cycle[color_idx % len(self.color_cycle)], linestyle=':', linewidth=0.8, alpha=0.5)
                plot_map = {1: show_e1, 2: show_e2, 3: show_e3}
                for i, color_offset in zip(plot_map.keys(), [0, 1, 2]):
                    if plot_map[i]:
                        current_color = self.color_cycle[(color_idx + color_offset) % len(self.color_cycle)]
                        if show_type != "เฉพาะค่า Imaginary": self.ax_mpt.plot(freq, results[f'eig{i}_real'], '-', color=current_color, label=f'{sample_label_short} E{i} (Real)')
                        if show_type != "เฉพาะค่า Real": self.ax_mpt.plot(freq, results[f'eig{i}_imag'], '--', color=current_color, label=f'{sample_label_short} E{i} (Imag)')
                color_idx += 3

        # พล็อตข้อมูลจากไฟล์ CSV
        if hasattr(self, 'mpt_loaded_csvs'):
            for path, csv_data in self.mpt_loaded_csvs.items():
                # *** เพิ่มเงื่อนไข Filter โลหะ ***
                if metal_filter != "All Metals" and not csv_data['label'].startswith(metal_filter):
                    continue

                if csv_data['var'].get() == 1:
                    plotted_something = True
                    # ... (โค้ดพล็อตส่วนที่เหลือเหมือนเดิม) ...
                    df = csv_data['df']; freq = df['Frequency']; label_short = csv_data['label']
                    plot_map = {1: show_e1, 2: show_e2, 3: show_e3}
                    for i, color_offset in zip(plot_map.keys(), [0, 1, 2]):
                         if plot_map[i]:
                            current_color = self.color_cycle[(color_idx + color_offset) % len(self.color_cycle)]
                            if show_type != "เฉพาะค่า Imaginary": self.ax_mpt.plot(freq, df[f'Eig{i}_Real'], '.-', color=current_color, label=f'{label_short} E{i} (Real)')
                            if show_type != "เฉพาะค่า Real": self.ax_mpt.plot(freq, df[f'Eig{i}_Imag'], ':x', color=current_color, label=f'{label_short} E{i} (Imag)')
                    color_idx += 3

        if plotted_something:
            legend = self.ax_mpt.legend(fontsize='small', loc='upper right')
            if legend:
                for text in legend.get_texts(): text.set_color("white" if ctk.get_appearance_mode() == "Dark" else "black")
        
        self.canvas_mpt.draw()

    def save_mpt_results(self, to_source=False):
        samples_to_save = [name for name, data in self.mpt_samples.items() if data.get('widgets', {}).get('sample_var', tkinter.IntVar(value=0)).get() and data.get('results')]
        if not samples_to_save: messagebox.showwarning("ไม่มีข้อมูล", "กรุณาเลือกและคำนวณชิ้นงานที่ต้องการบันทึก"); return
        save_dir = None
        if not to_source:
            save_dir = filedialog.askdirectory(title="เลือกโฟลเดอร์สำหรับบันทึกผล Eigenvalues");
            if not save_dir: self.log("ยกเลิกการบันทึก"); return
        saved_count = 0
        for sample_name in samples_to_save:
            try:
                results = self.mpt_samples[sample_name]['results']
                df_to_save = pd.DataFrame({'Frequency': results['freq'], 'Eig1_Real': results['eig1_real'], 'Eig1_Imag': results['eig1_imag'], 'Eig2_Real': results['eig2_real'], 'Eig2_Imag': results['eig2_imag'], 'Eig3_Real': results['eig3_real'], 'Eig3_Imag': results['eig3_imag']})
                filename = f"{sample_name}_Eigenvalues.csv"
                destination_dir = self.mpt_samples[sample_name]['path'] if to_source else save_dir
                save_path = os.path.join(destination_dir, filename)
                df_to_save.to_csv(save_path, index=False, float_format='%.6f')
                self.log(f"บันทึกไฟล์สำเร็จ: {save_path}"); saved_count += 1
            except Exception as e: self.log(f"ไม่สามารถบันทึกไฟล์สำหรับ {sample_name}: {e}")
        if saved_count > 0: messagebox.showinfo("บันทึกสำเร็จ", f"บันทึกข้อมูล Eigenvalues จำนวน {saved_count} ไฟล์เรียบร้อยแล้ว")

    def save_mpt_graph(self):
        self.log("กำลังเตรียมบันทึกกราฟ Eigenvalue...")
        try:
            save_path = filedialog.asksaveasfilename(title="บันทึกกราฟ Eigenvalue", defaultextension=".png", filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("All Files", "*.*")], initialfile="Eigenvalue_Analysis_Graph.png")
            if not save_path: self.log("ยกเลิกการบันทึกกราฟ"); return
            self.fig_mpt.savefig(save_path, dpi=300, bbox_inches='tight'); self.log(f"บันทึกกราฟสำเร็จ: {save_path}")
            messagebox.showinfo("บันทึกสำเร็จ", f"บันทึกกราฟแล้วที่:\n{save_path}")
        except Exception as e: self.log(f"เกิดข้อผิดพลาดในการบันทึกกราฟ: {e}"); messagebox.showerror("เกิดข้อผิดพลาด", f"ไม่สามารถบันทึกกราฟได้:\n{e}")
    # --- END: Eigenvalue (MPT) Tab Functions ---

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S"); full_message = f"[{timestamp}] {message}\n"
        self.log_textbox.configure(state="normal"); self.log_textbox.insert("end", full_message); self.log_textbox.configure(state="disabled"); self.log_textbox.see("end")

    def init_plot(self, fig, ax, canvas, title):
        is_dark = ctk.get_appearance_mode() == "Dark"; face_color = "#2B2B2B" if is_dark else "#F9F9F9"; text_color = "#DCE4EE" if is_dark else "#333333"; grid_color = 'gray'
        fig.patch.set_facecolor(face_color); ax.clear(); ax.set_facecolor(face_color)
        ax.set_xscale('log'); ax.set_xlabel('Frequency (Hz)', color=text_color); ax.set_ylabel('Impedance (Ohm)', color=text_color); ax.set_title(title, color=text_color)
        ax.grid(True, which="both", ls="--", color=grid_color, alpha=0.5); ax.tick_params(axis='x', colors=text_color); ax.tick_params(axis='y', colors=text_color)
        for spine in ax.spines.values(): spine.set_edgecolor(grid_color)
        if ax == self.ax_live: self.line_real, = self.ax_live.plot([], [], 'o-', label='Z Real'); self.line_imag, = self.ax_live.plot([], [], 'o-', label='Z Imaginary', color='r')
        legend = ax.legend();
        if legend:
            for text in legend.get_texts(): text.set_color(text_color)
            legend.get_frame().set_facecolor(face_color); legend.get_frame().set_edgecolor(grid_color)
        fig.tight_layout(); canvas.draw()

    def _find_all_summaries(self, folder):
        filepaths = [];
        for root, dirs, files in os.walk(folder):
            if "summary_results.csv" in files: filepaths.append(os.path.join(root, "summary_results.csv"))
        return filepaths
        
    def _reset_compare_filters(self):
        self.compare_direction_filter_var.set("All Directions"); self.compare_metal_filter_var.set("All Metals"); self.compare_plot_type_var.set("แสดงทั้งหมด (Both)")

    def load_compare_folder(self):
        self.log("กำลังเปิดหน้าต่างเลือกโฟลเดอร์เพื่อเปรียบเทียบ..."); initial_dir = "Measurement_Data" if os.path.isdir("Measurement_Data") else "."; folder = filedialog.askdirectory(title="Select a top-level folder to scan", initialdir=initial_dir)
        if not folder: self.log("ยกเลิกการเลือกโฟลเดอร์"); return
        filepaths = self._find_all_summaries(folder)
        if not filepaths: self.log(f"ไม่พบไฟล์ summary_results.csv ใน {folder}"); messagebox.showinfo("ไม่พบไฟล์", f"ไม่พบไฟล์ summary_results.csv ในโฟลเดอร์ที่เลือก"); return
        self._add_to_compare_list(filepaths, clear_existing=True)

    def load_compare_files(self):
        self.log("กำลังเปิดหน้าต่างเลือกไฟล์เพื่อเปรียบเทียบ..."); initial_dir = "Measurement_Data" if os.path.isdir("Measurement_Data") else "."; filepaths = filedialog.askopenfilenames(title="Select summary_results.csv files", filetypes=[("CSV Files", "*.csv")], initialdir=initial_dir)
        if not filepaths: self.log("ยกเลิกการเลือกไฟล์"); return
        self._add_to_compare_list(filepaths, clear_existing=False)

    def _add_to_compare_list(self, filepaths, clear_existing=False):
        if clear_existing:
            for widget in self.compare_list_frame.winfo_children(): widget.destroy()
            self.loaded_data_compare.clear(); self.compare_select_all_var.set(0); self._reset_compare_filters()
        for path in filepaths:
            if path in self.loaded_data_compare: continue
            try:
                label = self.get_label_from_path(path); cb = ctk.CTkCheckBox(self.compare_list_frame, text=label, command=self.redraw_comparison_plot)
                self.loaded_data_compare[path] = {'label': label, 'enabled_var': cb.get, 'checkbox': cb}; ToolTip(cb, text=label)
            except Exception as e: self.log(f"เกิดข้อผิดพลาดในการเพิ่มไฟล์ {os.path.basename(path)}: {e}")
        self._apply_compare_filters()
        
    def _apply_compare_filters(self, *args):
        direction_filter = self.compare_direction_filter_var.get(); metal_filter = self.compare_metal_filter_var.get()
        for data in self.loaded_data_compare.values():
            label, show_item = data['label'], True
            is_metal_data = any(m.lower() in label.lower() for m in self.metal_types)
            if is_metal_data:
                if metal_filter != "All Metals" and not label.lower().startswith(metal_filter.lower()): show_item = False
                if direction_filter != "All Directions" and f"_{direction_filter} " not in label and not label.endswith(f"_{direction_filter}"): show_item = False
            if show_item: data['checkbox'].pack(anchor="w", padx=5)
            else: data['checkbox'].pack_forget()
        self.redraw_comparison_plot()

    def _remove_selected_compare_items(self):
        paths_to_remove = [path for path, data in self.loaded_data_compare.items() if data['enabled_var']() == 1]
        if not paths_to_remove: messagebox.showinfo("ไม่มีรายการที่เลือก", "กรุณาเลือกรายการที่ต้องการลบ"); return
        if not messagebox.askyesno("ยืนยันการลบ", f"คุณต้องการลบ {len(paths_to_remove)} รายการที่เลือกใช่หรือไม่?"): return
        for path in paths_to_remove:
            if path in self.loaded_data_compare: del self.loaded_data_compare[path]
        self.redraw_comparison_plot(); self.log(f"ลบ {len(paths_to_remove)} รายการออกจากลิสต์แล้ว")

    def toggle_all_compare(self):
        new_state = self.compare_select_all_var.get()
        for data in self.loaded_data_compare.values():
            if data['checkbox'].winfo_manager():
                if new_state == 1: data['checkbox'].select()
                else: data['checkbox'].deselect()
        self.redraw_comparison_plot()

    def redraw_comparison_plot(self):
        self.init_plot(self.fig_compare, self.ax_compare, self.canvas_compare, "Comparison Plot"); color_idx = 0; plot_type = self.compare_plot_type_var.get()
        for path, data in self.loaded_data_compare.items():
            if data['checkbox'].winfo_manager() and data['enabled_var']() == 1:
                try:
                    df = pd.read_csv(path); color = self.color_cycle[color_idx % len(self.color_cycle)]; label = data['label']
                    if plot_type == "แสดงทั้งหมด (Both)":
                        self.ax_compare.plot(df['Frequency'], df['Z_Real'], 'o-', color=color, label=f'{label} (Real)'); self.ax_compare.plot(df['Frequency'], df['Z_Imaginary'], 'x--', color=color, label=f'{label} (Imag)')
                    elif plot_type == "เฉพาะค่า Real (Real Only)": self.ax_compare.plot(df['Frequency'], df['Z_Real'], 'o-', color=color, label=label)
                    elif plot_type == "เฉพาะค่า Imaginary (Imag Only)": self.ax_compare.plot(df['Frequency'], df['Z_Imaginary'], 'x--', color=color, label=label)
                    color_idx += 1
                except Exception as e: self.log(f"ไม่สามารถพล็อตกราฟจาก {os.path.basename(path)}: {e}")
        if color_idx > 0:
            legend = self.ax_compare.legend(fontsize='small');
            if legend:
                for text in legend.get_texts(): text.set_color("white" if ctk.get_appearance_mode() == "Dark" else "black")
        self.canvas_compare.draw()

    def _reset_calc_filters(self):
        self.calc_direction_filter_var.set("All Directions"); self.calc_metal_filter_var.set("All Metals"); self.calc_plot_type_var.set("แสดงทั้งหมด (Both)")

    def load_calc_folder(self):
        self.log("กำลังเปิดหน้าต่างเลือกโฟลเดอร์ Metal..."); initial_dir = os.path.join("Measurement_Data", "metal") if os.path.isdir(os.path.join("Measurement_Data", "metal")) else "."; folder = filedialog.askdirectory(title="Select a Metal folder to scan", initialdir=initial_dir)
        if not folder: self.log("ยกเลิกการเลือกโฟลเดอร์"); return
        filepaths = self._find_all_summaries(folder)
        if not filepaths: self.log(f"ไม่พบไฟล์ summary_results.csv ใน {folder}"); messagebox.showinfo("ไม่พบไฟล์", f"ไม่พบไฟล์ summary_results.csv ในโฟลเดอร์ที่เลือก"); return
        self._populate_calc_list(filepaths, clear_existing=True)

    def load_calc_file(self):
        self.log("กำลังเปิดหน้าต่างเลือกไฟล์ Metal..."); initial_dir = os.path.join("Measurement_Data", "metal") if os.path.isdir(os.path.join("Measurement_Data", "metal")) else "."; filepath = filedialog.askopenfilename(title="Select a single Metal summary_results.csv", filetypes=[("CSV Files", "*.csv")], initialdir=initial_dir)
        if not filepath: self.log("ยกเลิกการเลือกไฟล์"); return
        self._populate_calc_list([filepath], clear_existing=False)

    def _populate_calc_list(self, filepaths, clear_existing=False):
        if clear_existing:
            for widget in self.calc_list_frame.winfo_children(): widget.destroy()
            self.loaded_data_calc.clear(); self.calc_results_cache.clear()
            self.bg_for_metal_label.configure(text="N/A"); self.ferrite_label.configure(text="N/A"); self.bg_for_ferrite_label.configure(text="N/A")
            self.calc_select_all_var.set(0); self._reset_calc_filters()
        for path in filepaths:
            if path in self.loaded_data_calc: continue
            label = self.get_label_from_path(path); cb = ctk.CTkCheckBox(self.calc_list_frame, text=label, command=lambda p=path: self.on_calc_checkbox_toggle(p))
            self.loaded_data_calc[path] = {'label': label, 'enabled_var': cb.get, 'checkbox': cb}; ToolTip(cb, text=label)
        self._apply_calc_filters()

    def _apply_calc_filters(self, *args):
        direction_filter = self.calc_direction_filter_var.get(); metal_filter = self.calc_metal_filter_var.get()
        for data in self.loaded_data_calc.values():
            label, show_item = data['label'], True
            if metal_filter != "All Metals" and not label.lower().startswith(metal_filter.lower()): show_item = False
            if direction_filter != "All Directions" and f"_{direction_filter} " not in label and not label.endswith(f"_{direction_filter}"): show_item = False
            if show_item: data['checkbox'].pack(anchor="w", padx=5)
            else: data['checkbox'].pack_forget()
        self.redraw_calc_plot()
        
    def _remove_selected_calc_items(self):
        paths_to_remove = [path for path, data in self.loaded_data_calc.items() if data['enabled_var']() == 1]
        if not paths_to_remove: messagebox.showinfo("ไม่มีรายการที่เลือก", "กรุณาเลือกรายการที่ต้องการลบ"); return
        if not messagebox.askyesno("ยืนยันการลบ", f"คุณต้องการลบ {len(paths_to_remove)} รายการที่เลือกใช่หรือไม่?"): return
        for path in paths_to_remove:
            if path in self.loaded_data_calc:
                self.loaded_data_calc[path]['checkbox'].destroy(); del self.loaded_data_calc[path]; self.calc_results_cache.pop(path, None)
        self.redraw_calc_plot(); self.log(f"ลบ {len(paths_to_remove)} รายการออกจากลิสต์การคำนวณแล้ว")

    def toggle_all_calc(self):
        new_state = self.calc_select_all_var.get(); paths_to_process = []
        for path, data in self.loaded_data_calc.items():
            if data['checkbox'].winfo_manager():
                current_state = data['enabled_var']()
                if new_state == 1 and current_state == 0: data['checkbox'].select(); paths_to_process.append(path)
                elif new_state == 0 and current_state == 1: data['checkbox'].deselect()
        if new_state == 0: self.calc_results_cache.clear()
        else:
            for path in paths_to_process: self._perform_calculation_for_path(path)
        self.redraw_calc_plot()

    def on_calc_checkbox_toggle(self, path):
        self._find_associated_files(path)
        if self.loaded_data_calc[path]['enabled_var']() == 1 and path not in self.calc_results_cache: self._perform_calculation_for_path(path)
        self.redraw_calc_plot()

    def _perform_calculation_for_path(self, metal_path):
        self.log(f"กำลังคำนวณสำหรับ: {self.get_label_from_path(metal_path)}")
        try:
            paths = self._find_associated_files(metal_path)
            if not all([paths['bg_metal'], paths['ferrite'], paths['bg_ferrite']]): raise ValueError("ไม่พบไฟล์ที่เกี่ยวข้อง (Background/Ferrite) ครบถ้วน")
            df_metal, df_bg_metal, df_ferrite, df_bg_ferrite = pd.read_csv(paths['metal']), pd.read_csv(paths['bg_metal']), pd.read_csv(paths['ferrite']), pd.read_csv(paths['bg_ferrite'])
            freq_axis = np.logspace(np.log10(max(df_metal['Frequency'].min(), 1)), np.log10(df_metal['Frequency'].max()), 200)
            def interpolate_z(df, freqs): return np.interp(freqs, df['Frequency'], df['Z_Real']) + 1j * np.interp(freqs, df['Frequency'], df['Z_Imaginary'])
            z_metal, z_bg_metal, z_ferrite, z_bg_ferrite = interpolate_z(df_metal, freq_axis), interpolate_z(df_bg_metal, freq_axis), interpolate_z(df_ferrite, freq_axis), interpolate_z(df_bg_ferrite, freq_axis)
            z_bg_removed, z_calibrated_ferrite = z_metal - z_bg_metal, z_ferrite - z_bg_ferrite
            with np.errstate(divide='ignore', invalid='ignore'): z_final = np.divide(z_bg_removed, z_calibrated_ferrite); z_final[z_calibrated_ferrite == 0] = np.nan
            self.calc_results_cache[metal_path] = {'freq': freq_axis, 'z_final': z_final}; self.log(f"คำนวณสำเร็จ: {self.get_label_from_path(metal_path)}")
        except Exception as e:
            self.log(f"คำนวณล้มเหลวสำหรับ {self.get_label_from_path(metal_path)}: {e}")
            if metal_path in self.loaded_data_calc: self.loaded_data_calc[metal_path]['checkbox'].deselect()

    def redraw_calc_plot(self):
        self.init_plot(self.fig_calc, self.ax_calc, self.canvas_calc, "Calculation Result"); color_idx = 0; plot_type = self.calc_plot_type_var.get()
        for path, data in self.loaded_data_calc.items():
            if data['checkbox'].winfo_manager() and data['enabled_var']() == 1 and path in self.calc_results_cache:
                result = self.calc_results_cache[path]; color = self.color_cycle[color_idx % len(self.color_cycle)]
                label_real, label_imag = f"{data['label']} (Real)", f"{data['label']} (Imag)"
                if plot_type in ["แสดงทั้งหมด (Both)", "เฉพาะค่า Real (Real Only)"]: self.ax_calc.plot(result['freq'], result['z_final'].real, 'o-', ms=4, color=color, label=label_real)
                if plot_type in ["แสดงทั้งหมด (Both)", "เฉพาะค่า Imaginary (Imag Only)"]: self.ax_calc.plot(result['freq'], result['z_final'].imag, 'x--', ms=4, color=color, label=label_imag)
                color_idx += 1
        if color_idx > 0:
            legend = self.ax_calc.legend(fontsize='small');
            if legend:
                for text in legend.get_texts(): text.set_color("white" if ctk.get_appearance_mode() == "Dark" else "black")
        self.canvas_calc.draw()

    def _find_closest_file(self, target_dt, search_dir):
        if not os.path.isdir(search_dir): return None, None
        closest_path, min_delta = None, float('inf')
        for root, _, files in os.walk(search_dir):
            if "summary_results.csv" in files:
                timestamp_str = os.path.basename(root)
                try:
                    current_dt = datetime.strptime(timestamp_str, '%Y%m%d-%H%M%S'); delta = abs((target_dt - current_dt).total_seconds())
                    if delta < min_delta: min_delta, closest_path = delta, os.path.join(root, "summary_results.csv")
                except ValueError: continue
        return closest_path, min_delta

    def _find_associated_files(self, metal_path):
        paths = {'metal': metal_path, 'bg_metal': None, 'ferrite': None, 'bg_ferrite': None}
        try: metal_dt = datetime.strptime(os.path.basename(os.path.dirname(metal_path)), '%Y%m%d-%H%M%S')
        except ValueError: self.log(f"รูปแบบวันที่-เวลาของโฟลเดอร์ไม่ถูกต้องสำหรับ: {metal_path}"); return paths
        paths['bg_metal'], delta1 = self._find_closest_file(metal_dt, os.path.join("Measurement_Data", "background"))
        self.bg_for_metal_label.configure(text=f"{self.get_label_from_path(paths['bg_metal'])} (Δ {delta1:.0f}s)" if paths['bg_metal'] else "Not found")
        paths['ferrite'], delta2 = self._find_closest_file(metal_dt, os.path.join("Measurement_Data", "calibration"))
        self.ferrite_label.configure(text=f"{self.get_label_from_path(paths['ferrite'])} (Δ {delta2:.0f}s)" if paths['ferrite'] else "Not found")
        if paths['ferrite']:
            try:
                ferrite_dt = datetime.strptime(os.path.basename(os.path.dirname(paths['ferrite'])), '%Y%m%d-%H%M%S')
                paths['bg_ferrite'], delta3 = self._find_closest_file(ferrite_dt, os.path.join("Measurement_Data", "background"))
                self.bg_for_ferrite_label.configure(text=f"{self.get_label_from_path(paths['bg_ferrite'])} (Δ {delta3:.0f}s)" if paths['bg_ferrite'] else "Not found")
            except (ValueError, TypeError): self.bg_for_ferrite_label.configure(text="N/A (Error with Ferrite path)")
        else: self.bg_for_ferrite_label.configure(text="N/A (No Ferrite found)")
        return paths

    def save_calibrated_data(self, save_to_source=False):
        checked_paths = [path for path, data in self.loaded_data_calc.items() if data['checkbox'].winfo_manager() and data['enabled_var']() == 1 and path in self.calc_results_cache]
        if not checked_paths: messagebox.showwarning("No Data", "กรุณาเลือกและคำนวณข้อมูลที่ต้องการบันทึกก่อน"); return
        save_dir = None
        if not save_to_source:
            save_dir = filedialog.askdirectory(title="Select folder to save calibrated CSV files", initialdir="Measurement_Data" if os.path.isdir("Measurement_Data") else ".")
            if not save_dir: self.log("ยกเลิกการบันทึก"); return
        count = 0
        for path in checked_paths:
            try:
                result = self.calc_results_cache[path]; original_label = self.get_label_from_path(path).replace(' ', '_').replace('(', '').replace(')', '').replace(':', '')
                new_filename = f"{original_label}_CALIBRATED.csv"
                destination_dir = os.path.dirname(path) if save_to_source else save_dir
                save_path = os.path.join(destination_dir, new_filename)
                df_to_save = pd.DataFrame({'Frequency': result['freq'], 'Z_Calibrated_Real': result['z_final'].real, 'Z_Calibrated_Imag': result['z_final'].imag})
                df_to_save.to_csv(save_path, index=False); self.log(f"บันทึกไฟล์ Calibrated แล้ว: {new_filename}"); count += 1
            except Exception as e: self.log(f"ไม่สามารถบันทึกไฟล์สำหรับ {original_label}: {e}")
        if count > 0: messagebox.showinfo("บันทึกสำเร็จ", f"บันทึกข้อมูล Calibrated จำนวน {count} ไฟล์เรียบร้อยแล้ว")
        
    def save_calibrated_to_source(self): self.save_calibrated_data(save_to_source=True)
    def save_calibrated_to_new(self): self.save_calibrated_data(save_to_source=False)
    
    def get_label_from_path(self, path):
        if not path: return "N/A"
        try:
            parts = path.split(os.sep); base_index = parts.index('Measurement_Data'); info_parts = parts[base_index + 1:]
            measurement_type = info_parts[0]; timestamp_str = info_parts[-2]; dt_obj = datetime.strptime(timestamp_str, '%Y%m%d-%H%M%S'); formatted_time = dt_obj.strftime('%d-%b %H:%M')
            if measurement_type == 'metal' and len(info_parts) >= 5:
                metal = info_parts[1].capitalize(); sample = info_parts[2].replace('Sample_', 'S'); direction = info_parts[3].replace('Direction_', 'D'); return f"{metal}_{sample}_{direction} ({formatted_time})"
            else: return f"{measurement_type.capitalize()} ({formatted_time})"
        except (ValueError, IndexError): return os.path.basename(os.path.dirname(path))

    def start_measurement(self):
        if not self.validate_inputs(): return
        self.log("กำลังตรวจสอบค่าที่ป้อน..."); self.data_points = []; self.init_plot(self.fig_live, self.ax_live, self.canvas_live, "Live Impedance"); self.save_graph_button.configure(state="disabled")
        run_timestamp = time.strftime('%Y%m%d-%H%M%S'); measurement_folder_name = self.measurement_type.get()
        if measurement_folder_name == 'metal':
            metal_type = self.metal_type_combo.get(); sample_number = self.sample_num_entry.get(); direction = self.direction_entry.get()
            base_results_dir = os.path.join("Measurement_Data", measurement_folder_name, metal_type, f"Sample_{sample_number}", f"Direction_{direction}", run_timestamp)
        else: base_results_dir = os.path.join("Measurement_Data", measurement_folder_name, run_timestamp)
        self.current_results_dir = base_results_dir
        params = {'min_freq': float(self.min_freq_entry.get()), 'max_freq': float(self.max_freq_entry.get()), 'num_points': int(self.num_points_entry.get()), 'averages': int(self.averages_entry.get()), 'output_path': base_results_dir}
        self.set_ui_state_running(True); self.log(f"เริ่มการวัด: {measurement_folder_name}"); messagebox.showinfo("เริ่มต้นการวัด", f"ผลการวัดจะถูกบันทึกที่:\n{base_results_dir}")
        self.measurement_thread = MeasurementThread(params, self.queue_gui_update); self.measurement_thread.start()
        
    def stop_measurement(self):
        self.log("ส่งคำสั่งยกเลิกการวัด...");
        if self.measurement_thread and self.measurement_thread.is_alive(): self.measurement_thread.stop()
        self.set_ui_state_running(False); self.status_label.configure(text="สถานะ: ยกเลิกโดยผู้ใช้")
        
    def queue_gui_update(self, event_type, data): self.after(0, self.process_gui_update, event_type, data)
    
    def process_gui_update(self, event_type, data):
        if event_type == 'update':
            self.status_label.configure(text=data['status']); self.progress_bar.set(data['progress']); eta_seconds = data['eta']; hours, rem = divmod(eta_seconds, 3600); minutes, seconds = divmod(rem, 60)
            self.eta_label.configure(text=f"ETA: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"); point = data['point_data']; self.data_points.append(point)
            freqs, z_reals, z_imags = [p['freq'] for p in self.data_points], [p['z_real'] for p in self.data_points], [p['z_imag'] for p in self.data_points]
            self.line_real.set_data(freqs, z_reals); self.line_imag.set_data(freqs, z_imags)
            self.ax_live.relim(); self.ax_live.autoscale_view(); self.canvas_live.draw()
        elif event_type == 'finished':
            self.log("การวัดเสร็จสมบูรณ์!"); self.status_label.configure(text="สถานะ: การวัดเสร็จสมบูรณ์!"); self.save_graph_button.configure(state="normal")
            messagebox.showinfo("เสร็จสิ้น", f"การวัดเสร็จสมบูรณ์!\nไฟล์สรุปถูกบันทึกที่:\n{data['summary_path']}"); self.set_ui_state_running(False)
        elif event_type in ['cancelled', 'error']:
            if event_type == 'error': self.log(f"ข้อผิดพลาด: {data['error']}"); messagebox.showerror("เกิดข้อผิดพลาด", data['error'])
            self.log("การทำงานสิ้นสุดลง"); self.set_ui_state_running(False)
        elif event_type == 'log': self.log(data)

    def set_ui_state_running(self, is_running):
        state = "disabled" if is_running else "normal"
        live_tab_name = "🔴 Live Measurement"
        running_tab_name = "⏳ Live (Running...)"

        # 1. ควบคุมปุ่ม Start/Stop
        self.start_button.configure(state=state)
        self.stop_button.configure(state="normal" if is_running else "disabled")
        
        # 2. วนลูปเพื่อปิด/เปิดการใช้งานวิดเจ็ตทั้งหมดในแผงควบคุม
        # โดยไม่ปิดการใช้งานตัว ScrollableFrame โดยตรง
        widgets_to_toggle = self.setup_frame.winfo_children()[0].winfo_children()
        
        for widget in widgets_to_toggle:
            # ถ้าเป็น Frame (เช่น metal_frame) ให้วนลูปเข้าไปปิดวิดเจ็ตข้างในด้วย
            if isinstance(widget, ctk.CTkFrame):
                for child in widget.winfo_children():
                    try:
                        child.configure(state=state)
                    except (ValueError, tkinter.TclError):
                        pass # ข้ามวิดเจ็ตที่ไม่มี state เช่น Label
            else:
                try:
                    widget.configure(state=state)
                except (ValueError, tkinter.TclError):
                    pass # ข้ามวิดเจ็ตที่ไม่มี state เช่น Label

        # ถ้าไม่ใช่ตอนกำลังรัน ให้เรียกใช้ toggle_metal_widgets อีกครั้ง
        # เพื่อให้แน่ใจว่าสถานะของ metal frame ถูกต้องตามประเภทการวัดที่เลือก
        if not is_running:
            self.toggle_metal_widgets()

        # 3. เปลี่ยนชื่อแท็บเพื่อแสดงสถานะ
        if is_running:
            try:
                # ใช้ .tab().configure() แทน .rename() เพื่อความเข้ากันได้
                self.tab_view.tab(live_tab_name).configure(text=running_tab_name)
            except Exception as e:
                self.log(f"ไม่สามารถเปลี่ยนชื่อแท็บได้: {e}")
        else:
            try:
                self.tab_view.tab(running_tab_name).configure(text=live_tab_name)
            except Exception as e:
                self.log(f"ไม่สามารถเปลี่ยนชื่อแท็บกลับได้: {e}")
    
    def toggle_metal_widgets(self):
        is_running = self.start_button.cget('state') == 'disabled'
        state = "normal" if self.measurement_type.get() == "metal" and not is_running else "disabled"
        for widget in self.metal_frame.winfo_children():
             if not isinstance(widget, ctk.CTkLabel): widget.configure(state=state)

    def validate_inputs(self):
        try:
            min_f = float(self.min_freq_entry.get()); max_f = float(self.max_freq_entry.get()); points = int(self.num_points_entry.get()); avgs = int(self.averages_entry.get())
            if not (min_f > 0 and max_f > min_f and points > 1 and avgs > 0): raise ValueError("ค่าพารามิเตอร์ไม่ถูกต้อง (e.g., Freq Min > 0, Freq Max > Freq Min)")
            if self.measurement_type.get() == "metal": 
                if not self.metal_type_combo.get(): raise ValueError("กรุณาเลือกชนิดโลหะ")
                if not self.sample_num_entry.get(): raise ValueError("กรุณาใส่หมายเลขชิ้นงาน")
                sample = int(self.sample_num_entry.get()); direction = int(self.direction_entry.get())
                if not (1 <= direction <= 16): raise ValueError("Direction ต้องอยู่ระหว่าง 1-16")
            return True
        except ValueError as e: messagebox.showerror("ข้อมูลผิดพลาด", f"กรุณาตรวจสอบข้อมูลที่ป้อน: {e}"); return False
        except Exception as e: messagebox.showerror("ข้อมูลผิดพลาด", f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}"); return False

    def save_graph(self):
        if not self.current_results_dir: messagebox.showwarning("ไม่พร้อมบันทึก", "ยังไม่มีผลการวัดให้บันทึก"); return
        try:
            file_name = "summary_plots.png"; save_path = os.path.join(self.current_results_dir, file_name)
            self.fig_live.tight_layout(); self.fig_live.savefig(save_path, dpi=300, facecolor=self.fig_live.get_facecolor())
            self.log(f"บันทึกกราฟแล้วที่: {save_path}"); messagebox.showinfo("บันทึกสำเร็จ", f"บันทึกกราฟแล้วที่:\n{save_path}")
        except Exception as e: self.log(f"ไม่สามารถบันทึกกราฟได้: {e}"); messagebox.showerror("เกิดข้อผิดพลาด", f"ไม่สามารถบันทึกกราฟได้: {e}")

if __name__ == "__main__":
    try: from Background import Background
    except ImportError:
        class Background:
            def measure_impedance(self, frequency, averages):
                time.sleep(0.01) 
                z_real = 50 * np.log10(frequency/100) + np.random.randn() * 2
                z_imag = -30 * np.exp(-(frequency - 70000)**2 / (2*40000**2)) + np.random.randn() * 2
                z_mag = np.sqrt(z_real**2 + z_imag**2)
                z_phase = np.arctan2(z_imag, z_real)
                v_real, v_imag, i_real, i_imag = (1, 0, 0.02, -0.01)
                return complex(z_real, z_imag), z_mag, z_phase, z_real, z_imag, v_real, v_imag, i_real, i_imag
            def save_results(self, *args, **kwargs): pass
            def close(self): pass
            
    app = SweepApp()
    app.mainloop()