import time
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
import os
import pickle
import rp_scpi as scpi

class Background:
    def __init__(self, ip_address='rp-f05577.local', wave_form='sine', amplitude=40):
    #def __init__(self, ip_address='rp-f09afa.local', wave_form='sine', amplitude=40):
        """
        Initialize the Impedance Analyzer
        ปรับปรุงให้รองรับการแพร่คลื่นแค่หลากหลาย Decimation โดยเพิ่มความสามารถ _calculate_acquisition_parameters
        Parameters:
        -----------
        ip_address : str
            IP address or hostname of the Red Pitaya
        wave_form : str
            Signal waveform ('sine', 'square', etc.)
        amplitude : float
            Signal amplitude in volts
        """
        self.ip_address = ip_address
        self.wave_form = wave_form
        self.amplitude = float(int(amplitude) * 0.375 / 64) / 0.46251
        self.rp = None
        
        # Default acquisition parameters
        #self.data_size = 1024 * 16      
        #self.read_data_size = 1024 * 16
        #self.decimation = 256
        #self.sample_rate = 125e6 / self.decimation
        self.trigger_level = 0
        
        # Lists to store measurements
        self.v_list = []
        self.i_list = []
        self.z_list = []
        self.timestamps = []
        
        # Connect to Red Pitaya
        self._connect()
    
    def _connect(self):
        """Establish connection with the Red Pitaya"""
        try:
            self.rp = scpi.scpi(self.ip_address)
            print(f"\nConnected to Red Pitaya at {self.ip_address}")
        except Exception as e:
            print(f"Error connecting to Red Pitaya: {e}")
            self.rp = None
    
    def _calculate_acquisition_parameters(self, frequency):
        """
        *** เมธอดใหม่: คำนวณ Decimation และ Data Size ที่เหมาะสมที่สุดสำหรับความถี่ที่กำหนด ***
        """
        print(f"\nCalculating parameters for {frequency} Hz...")

        # ค่าคงที่สำหรับการคำนวณ
        BASE_CLOCK = 125e6  # 125 MHz
        MAX_BUFFER_SIZE = 16384 # ขนาด Buffer สูงสุดของ Red Pitaya
        SAMPLES_PER_PERIOD = 100 # จำนวนจุดข้อมูลที่ต้องการใน 1 ลูกคลื่น
        NUM_PERIODS = 5 # จำนวนลูกคลื่นที่ต้องการเก็บใน 1 การวัด

        # 1. คำนวณ Sampling Rate (fs) และ Decimation ที่เหมาะสม
        target_fs = frequency * SAMPLES_PER_PERIOD
        
        # ค่า Decimation ที่ Red Pitaya รองรับ
        #valid_decimations = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536]
        valid_decimations = [256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536]

        # คำนวณ decimation ที่ต้องการ
        ideal_decimation = BASE_CLOCK / target_fs
        
        # หาค่า decimation ที่เหมาะสมที่สุดจากลิสต์ที่ฮาร์ดแวร์รองรับ
        # (เลือกค่าแรกที่มากกว่าหรือเท่ากับค่า ideal ที่คำนวณได้)
        self.decimation = min([d for d in valid_decimations if d >= ideal_decimation], default=max(valid_decimations))
        
        # 2. คำนวณ Sample Rate จริงที่จะได้
        self.sample_rate = BASE_CLOCK / self.decimation

        # 3. คำนวณ Data Size ที่ต้องใช้
        # เราต้องมั่นใจว่าเก็บข้อมูลได้ครบตามจำนวนลูกคลื่นที่ต้องการ
        total_samples_needed = int(self.sample_rate / frequency * NUM_PERIODS)
        
        # ปรับขนาด data_size ให้ไม่เกิน buffer สูงสุด
        #self.data_size = min(total_samples_needed, MAX_BUFFER_SIZE)
        #self.read_data_size = self.data_size # จำนวนข้อมูลที่จะอ่านต่อครั้ง
        self.data_size = 1024 * 16
        self.read_data_size = 1024 * 16

        print(f"  - Target Sample Rate: ~{target_fs/1e3:.2f} kS/s")
        print(f"  - Calculated Decimation: {self.decimation}")
        print(f"  - Actual Sample Rate: {self.sample_rate/1e3:.2f} kS/s")
        print(f"  - Calculated Data Size: {self.data_size} samples")
    
    def _generate_signal(self, frequency):
        """Set up signal generator"""
        self.rp.tx_txt('GEN:RST')
        self.rp.tx_txt('SOUR1:FUNC ' + str(self.wave_form).upper())
        self.rp.tx_txt('SOUR1:FREQ:FIX ' + str(frequency))
        self.rp.tx_txt('SOUR1:VOLT ' + str(self.amplitude))
        
        # Enable output
        self.rp.tx_txt('OUTPUT1:STATE ON')
        #self.rp.tx_txt('SOUR1:TRig:INT')
        print(f"Generating {self.wave_form} signal at {frequency} Hz with {self.amplitude}V amplitude")
    
    def _setup_acquisition(self):
        """Set up the acquisition parameters"""
        # Reset Acquisition
        self.rp.tx_txt('ACQ:RST')
        
        # Get Memory region
        start_address = int(self.rp.txrx_txt('ACQ:AXI:START?'))
        size = int(self.rp.txrx_txt('ACQ:AXI:SIZE?'))
        start_address2 = round(start_address + size/2)
        
        print("start_address: ", start_address, "size: ", size, "Checked Address: ", bool(start_address/16777216), ", Check Size: ", bool(size/2097152))
        print(f"Reserved memory Start: {start_address:x} Size: {size:x}, Check Reserved memory: {bool(start_address / 0x1000000)}, Check Size: {bool(size / 0x200000)}\n")

        # Set decimation
        self.rp.tx_txt(f"ACQ:AXI:DEC {self.decimation}")
        print(f"Decimation set to {self.decimation}, Sample Rate: {self.sample_rate/1e6:.2f} MHz")
        
        # Set units
        self.rp.tx_txt('ACQ:AXI:DATA:Units VOLTS')
        
        # Set trigger delay for both channels
        self.rp.tx_txt(f"ACQ:AXI:SOUR1:Trig:Dly {self.data_size}")
        self.rp.tx_txt(f"ACQ:AXI:SOUR2:Trig:Dly {self.data_size}")
        
        # Set-up the Channel 1 and channel 2 buffers
        self.rp.tx_txt(f"ACQ:AXI:SOUR1:SET:Buffer {start_address},{size/2}")
        self.rp.tx_txt(f"ACQ:AXI:SOUR2:SET:Buffer {start_address2},{size/2}")
        
        # Enable DMA
        self.rp.tx_txt('ACQ:AXI:SOUR1:ENable ON')
        self.rp.tx_txt('ACQ:AXI:SOUR2:ENable ON')
        
        # Set trigger level
        self.rp.tx_txt(f"ACQ:TRig:LEV {self.trigger_level}")
        
        print('Acquisition setup complete')
    
    def _acquire_data(self, frequency):
        """Acquire data from the Red Pitaya"""
        # Start acquisition
        self.rp.tx_txt('ACQ:START')
        #self.rp.tx_txt('ACQ:TRig CH1_PE') # รอจับสัญญาณที่ "ขอบขาขึ้น" (Positive Edge) ของสัญญาณที่เข้ามาทาง Channel 1
        # VVV [แก้ไข] เปลี่ยนแหล่ง Trigger ไปที่ตัวกำเนิดสัญญาณ (AWG) VVV
        #self.rp.tx_txt('ACQ:TRig AWG_PE') 
        #self.rp.tx_txt('ACQ:TRig NOW')
        # 
        
        if frequency < 1000:
            print("Low frequency range detected. Using TRig AWG_PE.")
            # สำหรับความถี่ต่ำ: คำนวณพารามิเตอร์แบบไดนามิก
            self.rp.tx_txt('ACQ:TRig AWG_PE')
            #self.rp.tx_txt('ACQ:TRig CH1_PE')
        else:
            print("High frequency range detected. Using TRig CH1_PE.")
            # สำหรับความถี่สูง: ใช้ค่าคงที่ที่ทำงานได้ดี
            self.rp.tx_txt('ACQ:TRig CH1_PE')
         
        print("Waiting for trigger...")
        
        self.rp.tx_txt('SOUR1:TRig:INT')

        # Wait for trigger
        while True:
            self.rp.tx_txt("ACQ:TRig:STAT?")
            if self.rp.rx_txt() == 'TD':
                print("Triggered")
                time.sleep(1)
                break
        
        # Wait for buffer to fill
        while True:
            self.rp.tx_txt('ACQ:AXI:SOUR1:TRig:FILL?')
            if self.rp.rx_txt() == '1':
                print('DMA buffer full')
                break
        
        # Stop Acquisition
        self.rp.tx_txt('ACQ:STOP')
        
        # Get write pointer at trigger location
        pos_ch_a = int(self.rp.txrx_txt('ACQ:AXI:SOUR1:Trig:Pos?'))
        pos_ch_b = int(self.rp.txrx_txt('ACQ:AXI:SOUR2:Trig:Pos?'))
        
        # Read data
        self.rp.tx_txt(f"ACQ:AXI:SOUR1:DATA:Start:N? {pos_ch_a},{self.read_data_size}")
        signal_str_a = self.rp.rx_txt()
        self.rp.tx_txt(f"ACQ:AXI:SOUR2:DATA:Start:N? {pos_ch_b},{self.read_data_size}")
        signal_str_b = self.rp.rx_txt()
        
        # Parse data
        buff_voltage = list(map(float, signal_str_a.strip('{}\n\r').replace("  ", "").split(',')))
        buff_current = list(map(float, signal_str_b.strip('{}\n\r').replace("  ", "").split(',')))
        
        ## Processing
        voltage_signal = np.array(buff_voltage)
        current_signal = np.array(buff_current)

        #time_data_to_save = {'voltage': voltage_signal, 'current': current_signal, 'sample_rate': self.sample_rate}
        #timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        #pickle_filename = f'waveformData/run_{frequency}_{timestamp}.pkl'
        #with open(pickle_filename, 'wb') as pf:
        #    pickle.dump(time_data_to_save, pf)

        return np.array(buff_voltage), np.array(buff_current)
    
    def find_zero_crossings(self, data):
        """Find zero crossing indices to get full cycles"""
        return np.where(np.diff(np.signbit(data)))[0]

    def get_full_cycles(self, voltage, current):
        """Extract full cycles from the signals"""
        zero_crossings = self.find_zero_crossings(voltage)
        if len(zero_crossings) < 2:
            return voltage, current
        
        # Get complete cycles
        start_idx = zero_crossings[0]
        end_idx = zero_crossings[-1]
        if (end_idx - start_idx) % 2 != 0:  # Ensure we have complete cycles
            end_idx = zero_crossings[-2]
            
        return voltage[start_idx:end_idx], current[start_idx:end_idx]

    def calculate_fft(self, voltage, current, frequency):
        """Calculate FFT of the signals"""
        sample_rate = 125e6 / self.decimation

        n = len(voltage)
        if n == 0: return {}
        # สร้างและใช้ Hanning Window เพื่อลด Spectral Leakage
        window = np.hanning(n)
        voltage_win = voltage * window
        current_win = current * window

        # Calculate FFT
        v_fft = np.fft.fft(voltage_win)
        i_fft = np.fft.fft(current_win)        

        #v_fft = np.fft.fft(voltage)
        #i_fft = np.fft.fft(current)


        # Frequency axis
        freq_axis = np.fft.fftfreq(len(v_fft), d=1/sample_rate)

        # Find frequency index
        #freq_idx = int(len(v_fft) * frequency / sample_rate)
        freq_idx = np.argmin(abs(freq_axis - frequency))        
        
        return v_fft[freq_idx], i_fft[freq_idx]
    
    def calculate_z(self, v_fft, i_fft):
        """Calculate impedance using FFT"""
        # Calculate impedance at the fundamental frequency
        z = v_fft / i_fft
        z_magnitude = np.abs(z)
        z_phase = np.angle(z, deg=True)
        z_real = np.real(z)
        z_imag = np.imag(z)
        
        return z, z_magnitude, z_phase, z_real, z_imag

    def measure_voltage_current(self, frequency, num_averages=3):
        """
        Measure ADC at a specific FFT in peak frequency with averaging
        
        Parameters:
        -----------
        frequency : float
            Frequency in Hz to measure impedance at
        num_averages : int
            Number of measurements to average
            
        Returns:
        --------
        avg_v : complex
            Average voltage value
        avg_i : complex
            Average current value
        """
        # Clear previous measurements
        self.v_list = []
        self.i_list = []
        self.timestamps = []
        
        # Run multiple measurements for averaging
        for avg in range(num_averages):
            print(f"\nMeasurement {avg+1} of {num_averages}")
            
            # Calculate acquisition parameters
            self._calculate_acquisition_parameters(frequency)

            # Generate signal
            self._generate_signal(frequency)
            
            # Setup acquisition
            self._setup_acquisition()
            
            # Acquire data
            raw_voltage, raw_current = self._acquire_data(frequency)
            
            # Process data
            voltage, current = self.get_full_cycles(raw_voltage, raw_current)
            
            # Calculate FFT
            v_fft, i_fft = self.calculate_fft(voltage, current, frequency)
            
            # Store results
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.v_list.append(v_fft)
            self.i_list.append(i_fft)
            self.timestamps.append(timestamp)
            
            # Print results
            print(f"Timestamp: {timestamp}")
            print(f"Frequency: {frequency} Hz")
            print(f"Complex Voltage (V): {v_fft}")
            print(f"Complex Current (I): {i_fft}")
        
        # Calculate averages
        avg_v = np.mean(self.v_list)
        avg_i = np.mean(self.i_list)
        
        print("\nAverage Results:")
        print(f"Average Voltage: {avg_v:f} V")
        print(f"Average Current: {avg_i:f} A")
        
        return avg_v, avg_i        

    def calculate_impedance(self, voltage, current, frequency):
        """Calculate impedance using FFT"""
        sample_rate = 125e6 / self.decimation
        
        v_fft = np.fft.fft(voltage)
        i_fft = np.fft.fft(current)
        
        # Frequency axis
        freq_axis = np.fft.fftfreq(len(v_fft), d=1/sample_rate)

        # Find frequency index
        #freq_idx = int(len(v_fft) * frequency / sample_rate)
        freq_idx = np.argmin(abs(freq_axis - frequency))  
        
        # Calculate impedance at the fundamental frequency
        z = v_fft[freq_idx] / i_fft[freq_idx]
        z_magnitude = np.abs(z)
        z_phase = np.angle(z, deg=True)
        z_real = np.real(z)
        z_imag = np.imag(z)
        
        return z, z_magnitude, z_phase, z_real, z_imag, v_fft[freq_idx], i_fft[freq_idx]
    
    def measure_impedance(self, frequency, num_averages=3):
        """
        Measure impedance at a specific frequency with averaging
        
        Parameters:
        -----------
        frequency : float
            Frequency in Hz to measure impedance at
        num_averages : int
            Number of measurements to average
            
        Returns:
        --------
        complex_z : complex
            Complex impedance value
        z_magnitude : float
            Impedance magnitude
        z_phase : float
            Impedance phase in degrees
        """
        # Clear previous measurements
        self.v_list = []
        self.i_list = []
        self.z_list = []
        self.timestamps = []
        
        # Run multiple measurements for averaging
        for avg in range(num_averages):
            print(f"\nMeasurement {avg+1} of {num_averages}")

            if frequency < 1000:
                print("Low frequency range detected. Using dynamic parameters.")
                # สำหรับความถี่ต่ำ: คำนวณพารามิเตอร์แบบไดนามิก
                self._calculate_acquisition_parameters(frequency)
            else:
                print("High frequency range detected. Using fixed parameters.")
                # สำหรับความถี่สูง: ใช้ค่าคงที่ที่ทำงานได้ดี
                self.decimation = 256
                self.data_size = 1024 * 16
                self.read_data_size = 1024 * 16
                self.sample_rate = 125e6 / self.decimation                

            # Generate signal
            self._generate_signal(frequency)
            
            # Setup acquisition
            self._setup_acquisition()
            
            # Acquire data
            raw_voltage, raw_current = self._acquire_data(frequency)
            
            # Process data
            voltage, current = self.get_full_cycles(raw_voltage, raw_current)
            
            '''
            # plot the acquired signals
            plt.figure(figsize=(12, 6))
            plt.subplot(2, 1, 1)
            plt.plot(raw_voltage, label='Voltage Signal', color='blue')
            plt.plot(voltage, label='Processed Voltage Signal', color='green')
            plt.title('Acquired Voltage Signal')
            plt.xlabel('Sample Number')
            plt.ylabel('Voltage (V)')
            plt.grid(True)
            plt.legend()
            plt.subplot(2, 1, 2)
            plt.plot(raw_current, label='Current Signal', color='orange')
            plt.plot(current, label='Processed Current Signal', color='red')
            plt.title('Acquired Current Signal')
            plt.xlabel('Sample Number')
            plt.ylabel('Current (A)')
            plt.grid(True)
            plt.legend()            
            plt.tight_layout()
            plt.show()
            '''

            # Calculate impedance
            z, z_magnitude, z_phase, z_real, z_imag, v_fft, i_fft = self.calculate_impedance(
                voltage, current, frequency)
            
            # Store results
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.v_list.append(v_fft)
            self.i_list.append(i_fft)
            self.z_list.append(z)
            self.timestamps.append(timestamp)
            
            # Print results
            print(f"Timestamp: {timestamp}")
            print(f"Frequency: {frequency} Hz")
            print(f"Impedance Magnitude: {z_magnitude:f} ohm")
            print(f"Impedance Phase: {z_phase:f} degrees")
            print(f"Impedance Real Part: {z_real:f} ohm")
            print(f"Impedance Imaginary Part: {z_imag:f} ohm")
            print(f"Voltage (V): {v_fft} V")
            print(f"Current (I): {i_fft} V")
        
        # Calculate averages
        avg_v = np.mean(self.v_list)
        #avg_v = np.max(self.v_list)
        v_real_avg = np.real(avg_v)
        v_imag_avg = np.imag(avg_v)
        avg_i = np.mean(self.i_list)
        #avg_i = np.max(self.i_list)
        i_real_avg = np.real(avg_i)
        i_imag_avg = np.imag(avg_i)
        avg_z = np.mean(self.z_list)
        #avg_z = np.max(self.z_list)
        z_magnitude_avg = np.abs(avg_z)
        z_phase_avg = np.angle(avg_z, deg=True)
        z_real_avg = np.real(avg_z)
        z_imag_avg = np.imag(avg_z)
        se_v        = np.std(self.v_list, ddof=1) / np.sqrt(len(self.v_list))
        se_v_pct    = se_v / np.abs(avg_v) * 100
        
        print("\nAverage Results:")
        print(f"Average Impedance: {z_magnitude_avg:f} ∠ {z_phase_avg:f}° ohm")
        print(f"Average Real Part: {z_real_avg:f} ohm")
        print(f"Average Imaginary Part: {z_imag_avg:f} ohm")
        print(f"Average Voltage: {v_real_avg:f} + j{v_imag_avg:f} V")
        print(f"Average Current: {i_real_avg:f} + j{i_imag_avg:f} A")
        print(f"SD Voltage: {np.std(self.v_list, ddof=1):f}")
        print(f"Error Voltage: {np.std(self.v_list) / np.sqrt(len(self.v_list)):f}")
        print(f"SE Voltage = {se_v:.4g}  →  {se_v_pct:.2f}% ของค่าเฉลี่ย")
        print(f"SD Current: {np.std(self.i_list):f}") 
        print(f"Error Current: {np.std(self.i_list) / np.sqrt(len(self.i_list)):f}")
        
        return avg_z, z_magnitude_avg, z_phase_avg, z_real_avg, z_imag_avg, v_real_avg, v_imag_avg, i_real_avg, i_imag_avg
    
    def plot_results(self):
        """Plot the measurement results"""
        sample_rate = 125e6 / self.decimation
        
        # Create figure
        plt.switch_backend('MacOSX')
        fig = plt.figure(figsize=(12, 7))
        
        # Plot subplots for each measurement run
        for i, (v, i, z) in enumerate(zip(self.v_list, self.i_list, self.z_list)):
            # Create time axis for this dataset
            time_axis = np.arange(len(v)) / sample_rate
            
            # Plot voltage
            plt.subplot(3, 1, 1)
            plt.plot(time_axis, v, label=f'Run {i+1}', alpha=0.7)
            
            # Plot current
            plt.subplot(3, 1, 2)
            plt.plot(time_axis, i, label=f'Run {i+1}', alpha=0.7)
        
        plt.subplot(3, 1, 1)
        plt.title('Voltage Measurements')
        plt.xlabel('Time (s)')
        plt.ylabel('Voltage (V)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        plt.subplot(3, 1, 2)
        plt.title('Current Measurements')
        plt.xlabel('Time (s)')
        plt.ylabel('Current (A)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Calculate average Z
        avg_z = np.mean(self.z_list)
        z_magnitude_avg = np.abs(avg_z)
        z_phase_avg = np.angle(avg_z, deg=True)
        
        # Plot impedance magnitude and phase
        plt.subplot(3, 1, 3)
        magnitudes = [np.abs(z) for z in self.z_list]
        phases = [np.angle(z, deg=True) for z in self.z_list]
        x = np.arange(len(self.z_list))
        plt.bar(x, magnitudes, width=0.4, label='|Z|')
        plt.plot(x, phases, 'ro-', label='Phase (°)')
        plt.title(f'Average Impedance: {z_magnitude_avg:.2f} ∠ {z_phase_avg:.2f}° ohm')
        plt.xlabel('Measurement Run')
        plt.ylabel('Impedance (ohm) / Phase (°)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Plot real and imaginary parts
        plt.figure(figsize=(10, 5))
        plt.subplot(2, 1, 1)
        real_parts = [np.real(z) for z in self.z_list]
        plt.bar(x, real_parts, width=0.4, color='blue', label='Re(Z)')
        plt.title('Real Part of Impedance')
        plt.xlabel('Measurement Run')
        plt.ylabel('Real(Z) (ohm)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        plt.subplot(2, 1, 2)
        imag_parts = [np.imag(z) for z in self.z_list]
        plt.bar(x, imag_parts, width=0.4, color='orange', label='Im(Z)')
        plt.title('Imaginary Part of Impedance')
        plt.xlabel('Measurement Run')
        plt.ylabel('Imag(Z) (ohm)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Adjust layout
        plt.tight_layout(h_pad=1.5)
        plt.show()
    
    def save_results(self, frequency, results_dir=None, base_name=None, file_extension=None):
        """
        Save results to file
        
        Parameters:
        -----------
        frequency : float
            Frequency in Hz used for measurement
        results_dir : str, optional
            Directory to save results (default: "test_results")
        base_name : str, optional
            Base name for the file (default: f'impedance_f{frequency}_dec{self.decimation}_avg{len(self.z_list)}')
        file_extension : str, optional
            File extension to use (default: ".txt")

        Example:
        --------
        analyzer = ImpedanceAnalyzer()
        analyzer.save_results(frequency, results_dir="custom_results")
        analyzer.save_results(frequency, base_name=f"my_measurement_{frequency}")
        analyzer.save_results(frequency, file_extension=".csv")
        analyzer.save_results(
            frequency, 
            results_dir="my_results",
            base_name=f"impedance_measurement_{time.strftime('%Y%m%d_%H%M%S')}",
            file_extension=".dat"
        )
        
        """

        # Use default values if parameters are not provided
        if results_dir is None:
            results_dir = "test_results"
        
        if base_name is None:
            base_name = f'impedance_f{frequency}_dec{self.decimation}_avg{len(self.z_list)}'
        
        if file_extension is None:
            file_extension = ".txt"
        
        # Ensure file extension starts with a dot
        if not file_extension.startswith('.'):
            file_extension = '.' + file_extension
        
        # Create full file path
        txt_file = os.path.join(results_dir, f"{base_name}{file_extension}")
        
        # Create directory if it doesn't exist
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
        
        print(f"Saving results to: {txt_file}")
        
        # Calculate average Z
        avg_z = np.mean(self.z_list)
        #avg_z = np.max(self.z_list)
        z_magnitude_avg = np.abs(avg_z)
        z_phase_avg = np.angle(avg_z, deg=True)
        z_real_avg = np.real(avg_z)
        z_imag_avg = np.imag(avg_z)
        avg_voltage = np.mean(self.v_list)
        #avg_voltage = np.max(self.v_list)
        std_voltage = np.std(self.v_list)
        err_voltage = np.std(self.v_list) / np.sqrt(len(self.v_list))
        avg_current = np.mean(self.i_list)
        #avg_current = np.max(self.i_list)
        std_current = np.std(self.i_list)
        err_current = np.std(self.i_list) / np.sqrt(len(self.i_list))
        
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        
        with open(txt_file, "w", encoding="utf-8") as fp:
            fp.write(f"Timestamp: {timestamp}\n")
            fp.write(f"Frequency: {frequency} Hz\n")
            fp.write(f"Impedance Magnitude: {z_magnitude_avg:f} ohm\n")
            fp.write(f"Impedance Phase: {z_phase_avg:f} degrees\n")
            fp.write(f"Impedance Real Part: {z_real_avg:f} ohm\n")
            fp.write(f"Impedance Imaginary Part: {z_imag_avg:f} ohm\n")
            fp.write(f"Average Voltage: {avg_voltage:f} V\n")
            fp.write(f"Average Current: {avg_current:f} A\n")
            fp.write(f"Standard Deviation Voltage: {std_voltage:f} V\n")
            fp.write(f"Standard Deviation Current: {std_current:f} A\n")
            fp.write(f"Error Voltage: {err_voltage:f} V\n")
            fp.write(f"Error Current: {err_current:f} A\n\n")
            
            
            fp.write("Individual Measurements:\n")
            for idx, (timestamp, z) in enumerate(zip(self.timestamps, self.z_list)):
                mag = np.abs(z)
                phase = np.angle(z, deg=True)
                real = np.real(z)
                imag = np.imag(z)
                fp.write(f"Run {idx+1} [{timestamp}]:\n")
                fp.write(f"  |Z| = {mag:f} ohm, Phase = {phase:f}°\n")
                fp.write(f"  Re(Z) = {real:f} ohm, Im(Z) = {imag:f} ohm\n")
                fp.write(f"  Voltage (V): {self.v_list[idx]}\n")
                fp.write(f"  Current (I): {self.i_list[idx]}\n")
                fp.write("\n")               
    
    def close(self):
        """Close the connection to Red Pitaya"""
        if self.rp:
            self.rp.tx_txt('ACQ:AXI:SOUR1:ENable OFF')
            self.rp.tx_txt('ACQ:AXI:SOUR2:ENable OFF')
            self.rp.close()
            print("Connection to Red Pitaya closed")