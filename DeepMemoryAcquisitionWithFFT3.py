import time
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
import tkinter as tk
import os
import rp_scpi as scpi

IP = 'rp-f05577.local'
#IP = 'rp-f09afa.local'          # local IP of Red Pitaya
rp = scpi.scpi(IP)            # open socket connection with Red Pitaya


## Generate signal----------------------------------------------------
wave_form = 'sine'
freq = 500  # Set your desired frequency
ampl = 0.5   # Set your desired amplitude

average = 3
v_list = []
i_list = []
z_list = []
timestamps = []

for avg in range(average):
    rp.tx_txt('GEN:RST')

    rp.tx_txt('SOUR1:FUNC ' + str(wave_form).upper())
    rp.tx_txt('SOUR1:FREQ:FIX ' + str(freq))
    rp.tx_txt('SOUR1:VOLT ' + str(ampl))

    # Enable output
    rp.tx_txt('OUTPUT1:STATE ON')
    rp.tx_txt('SOUR1:TRig:INT')

    print("Generate signal")

    ## Acquisition parameters-----------------------------------------------
    ## size in samples 16Bit
    DATA_SIZE = 4096 * 16          # ((1024 * 1024 * 128) / 2)        ## for 128 MB ##
    READ_DATA_SIZE = 4096 * 16     # (1024 * 256)                     ## for 128 MB ##

    dec = 625
    trig_lvl = 0

    print("Start program")
    ## Reset Acquisition
    rp.tx_txt('ACQ:RST')

    # Get Memory region
    start_address = int(rp.txrx_txt('ACQ:AXI:START?'))
    size = int(rp.txrx_txt('ACQ:AXI:SIZE?'))
    start_address2 = round(start_address + size/2)

    print(start_address)
    print(size)

    print("start_address: ", start_address, "size: ", size, "Checked Address: ", bool(start_address/16777216), ", Check Size: ", bool(size/2097152))
    print(f"Reserved memory Start: {start_address:x} Size: {size:x}, Check Reserved memory: {bool(start_address / 0x1000000):.2f}, Check Size: {bool(size / 0x200000):.2f}\n")

    # Set decimation
    rp.tx_txt(f"ACQ:AXI:DEC {dec}")

    # Set units
    rp.tx_txt('ACQ:AXI:DATA:Units VOLTS')

    # Set trigger delay for both channels
    rp.tx_txt(f"ACQ:AXI:SOUR1:Trig:Dly {DATA_SIZE}")
    rp.tx_txt(f"ACQ:AXI:SOUR2:Trig:Dly {DATA_SIZE}")

    # Set-up the Channel 1 and channel 2 buffers to each work with half the available memory space.
    rp.tx_txt(f"ACQ:AXI:SOUR1:SET:Buffer {start_address},{size/2}")
    rp.tx_txt(f"ACQ:AXI:SOUR2:SET:Buffer {start_address2},{size/2}")

    # Enable DMA
    rp.tx_txt('ACQ:AXI:SOUR1:ENable ON')
    rp.tx_txt('ACQ:AXI:SOUR2:ENable ON')
    print('Enable CHA and CHB\n')

    # Specify the acquisition trigger
    rp.tx_txt(f"ACQ:TRig:LEV {trig_lvl}")


    ## ACQUISITION

    rp.tx_txt('ACQ:START')
    rp.tx_txt('ACQ:TRig CH1_PE')


    print("Waiting for trigger\n")

    # Wait for trigger
    while 1:
        rp.tx_txt("ACQ:TRig:STAT?")
        if rp.rx_txt() == 'TD':
            print("Triggered")
            time.sleep(0.5)
            break

    # wait for fill adc buffer
    while 1:
        rp.tx_txt('ACQ:AXI:SOUR1:TRig:FILL?')
        if rp.rx_txt() == '1':
            print('DMA buffer full\n')
            break

    # Stop Acquisition
    rp.tx_txt('ACQ:STOP')

    ## Get write pointer at trigger location
    posChA = int(rp.txrx_txt('ACQ:AXI:SOUR1:Trig:Pos?'))
    posChB = int(rp.txrx_txt('ACQ:AXI:SOUR2:Trig:Pos?'))
    print(posChA, posChB)

    ## Read & plot

    rp.tx_txt(f"ACQ:AXI:SOUR1:DATA:Start:N? {posChA},{READ_DATA_SIZE}")
    signal_str = rp.rx_txt()
    rp.tx_txt(f"ACQ:AXI:SOUR2:DATA:Start:N? {posChB},{READ_DATA_SIZE}")
    signal_str2 = rp.rx_txt()

    print("Data Acquired\n")

    buff1 = list(map(float, signal_str.strip('{}\n\r').replace("  ", "").split(',')))
    buff2 = list(map(float, signal_str2.strip('{}\n\r').replace("  ", "").split(',')))

    ## Acquisition and Processing Functions
    def find_zero_crossings(data):
        """Find zero crossing indices to get full cycles"""
        return np.where(np.diff(np.signbit(data)))[0]

    def get_full_cycles(voltage, current, sample_rate):
        """Extract full cycles from the signals"""
        zero_crossings = find_zero_crossings(voltage)
        if len(zero_crossings) < 2:
            return voltage, current
        
        # Get complete cycles
        start_idx = zero_crossings[0]
        end_idx = zero_crossings[-1]
        if (end_idx - start_idx) % 2 != 0:  # Ensure we have complete cycles
            end_idx = zero_crossings[-2]
            
        return voltage[start_idx:end_idx], current[start_idx:end_idx]

    def calculate_impedance(voltage, current, freq):
        """Calculate impedance using FFT"""
        v_fft = np.fft.fft(voltage)
        i_fft = np.fft.fft(current)
        
        # Find frequency index
        freq_idx = int(len(v_fft) * freq / sample_rate)
        
        # Calculate impedance at the fundamental frequency
        z = v_fft[freq_idx] / i_fft[freq_idx]
        z_magnitude = np.abs(z)
        z_phase = np.angle(z, deg=True)
        z_real = np.real(z)
        z_imag = np.imag(z)
        print(f"Complex Voltage (V): {v_fft[freq_idx]}")
        print(f"Complex Current (I): {i_fft[freq_idx]}")
        print(f"Complex Impedance (Z): {z}")
        return z, z_magnitude, z_phase, z_real, z_imag

    # Modify sampling rate based on decimation
    sample_rate = 125e6 / dec  # Red Pitaya's base sample rate is 125 MHz

    # After acquiring data and converting to buff1 (voltage) and buff2 (current)
    voltage, current = get_full_cycles(np.array(buff1), np.array(buff2), sample_rate)

    # Calculate impedance
    z, z_magnitude, z_phase, z_real, z_imag = calculate_impedance(voltage, current, freq)

    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"Timestamp: {ts}")
    print(f"Frequency: {freq} Hz\n")
    print(f"Impedance Magnitude: {z_magnitude:.2f} ohm")
    print(f"Impedance Phase: {z_phase:.2f} degrees\n")
    print(f"Impedance Real Part: {z_real:.2f} ohm") 
    print(f"Impedance Imaginary Part: {z_imag:.2f} ohm")



    v_list.append(voltage)
    i_list.append(current)
    z_list.append(z)
    timestamps.append(ts)

print(f"Collected {len(v_list)} voltage measurements")
print(f"Collected {len(i_list)} current measurements")
print(f"Collected {len(z_list)} impedance measurements")

# Calculate the average complex impedance directly
avg_Z = np.mean(z_list)
z_magnitude_avg = np.abs(avg_Z)
z_phase_avg = np.angle(avg_Z, deg=True)
z_real_avg = np.real(avg_Z)
z_imag_avg = np.imag(avg_Z)

print(f"Average Impedance: {z_magnitude_avg:f} ∠ {z_phase_avg:f}° ohm")
print(f"Average Impedance Real Part: {z_real_avg:f} ohm")
print(f"Average Impedance Imaginary Part: {z_imag_avg:f} ohm")

# Calculate average voltage, current, and impedance for each frequency
avg_voltage = np.mean([np.mean(v) for v in v_list])
avg_current = np.mean([np.mean(i) for i in i_list])
avg_impedance = np.mean([np.mean(z) for z in z_list])

print(f"Average Voltage: {avg_voltage:f} V")
print(f"Average Current: {avg_current:f} A")
print(f"Average Impedance: {avg_impedance:f} ohm")
# Print the average values

# Plotting

# Create figure with full screen size for Mac
plt.switch_backend('MacOSX')
screen_dpi = plt.rcParams['figure.dpi']
fig = plt.figure(figsize=(12, 7))

# Plot subplots for each measurement run
for i, (v, i, z) in enumerate(zip(v_list, i_list, z_list)):
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

# Plot impedance magnitude and phase
plt.subplot(3, 1, 3)
magnitudes = [np.abs(z) for z in z_list]
phases = [np.angle(z, deg=True) for z in z_list]
x = np.arange(len(z_list))
plt.bar(x, magnitudes, width=0.4, label='|Z|')
plt.plot(x, phases, 'ro-', label='Phase (°)')
plt.title(f'Average Impedance: {z_magnitude_avg:f} ∠ {z_phase_avg:f}° ohm')
plt.xlabel('Measurement Run')
plt.ylabel('Impedance (ohm) / Phase (°)')
plt.grid(True, alpha=0.3)
plt.legend()

# Plot real and imaginary parts of impedance
plt.figure(figsize=(10, 5))
plt.subplot(2, 1, 1)
real_parts = [np.real(z) for z in z_list]
plt.bar(x, real_parts, width=0.4, color='blue', label='Re(Z)')
plt.title('Real Part of Impedance')
plt.xlabel('Measurement Run')
plt.ylabel('Real(Z) (ohm)')
plt.grid(True, alpha=0.3)
plt.legend()

plt.subplot(2, 1, 2)
imag_parts = [np.imag(z) for z in z_list]
plt.bar(x, imag_parts, width=0.4, color='orange', label='Im(Z)')
plt.title('Imaginary Part of Impedance')
plt.xlabel('Measurement Run')
plt.ylabel('Imag(Z) (ohm)')
plt.grid(True, alpha=0.3)
plt.legend()

# Adjust layout
plt.tight_layout(h_pad=1.5)

# Adjust layout
plt.tight_layout(h_pad=1.5)

# Show plot
plt.show()

# Create results directory if it doesn't exist
results_dir = "DeepMemoryAcquisitionWithFFT_results"
base_name = f'error_dec{dec}_avg{average}'
txt_file = os.path.join(results_dir, f"{base_name}.txt")

if not os.path.exists(results_dir):
    os.makedirs(results_dir)

print(f"Saving .txt to: {txt_file}")

# Save results to file
with open(txt_file, "w", encoding="utf-8") as fp:
    fp.write(f"Frequency: {freq} Hz\n")
    fp.write(f"Average Voltage: {avg_voltage:f} V\n")
    fp.write(f"Average Current: {avg_current:f} A\n")
    fp.write(f"Average Impedance: {avg_impedance:f} ohm\n")
    fp.write("\n")

# Move this code outside the loop:
rp.tx_txt('ACQ:AXI:SOUR1:ENable OFF')
rp.tx_txt('ACQ:AXI:SOUR2:ENable OFF')
print('Releasing resources\n')
print("End program")
rp.close()

