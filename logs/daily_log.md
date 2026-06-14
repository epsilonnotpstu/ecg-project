Day X - [14/06]
Phase E - Recording Sessions
Created and tested scripts/record_session.py

Recording duration: 15 seconds

Sample count: [insert actual count, e.g., 3712]3500+ every moment

Lead-off count:  file="afriditest01_20260614_142501.csv"
awk -F',' '$3==0' raw/esp/$file | wc -l
0
 

Output file: raw/esp/test01_20260614_153000.csv

Observation: [describe signal quality ? rhythm visible / noisy / etc.]
rhythm visible
Problems
[Write down any problems, or ?None? if no issues] no issu found

Next
Phase F ? Begin signal filtering
Phase F - Signal Filtering
Updated scripts/filter_signal.py: 50Hz notch filter + 0.5?40Hz bandpass

Input file: raw/esp/afridi_test.csv (15s recording, ~236Hz effective rate)

FFT analysis: dominant noise at 50Hz (powerline interference)

Output: filtered/esp/afridi_test_filtered.csv

Comparison plot: raw/esp/afridi_test_compare.png

Result: clear QRS complex pattern visible in filtered signal, 22 R-peaks detected

Estimated BPM: 83.1 (within normal range)

Observation: ADC saturation at R-peak (72 samples at value 1024) ? note for future morphology analysis, not blocking current phase

Problems
None

Next
Create a separate peak detection script (bpm_detect.py) to consistently calculate BPM across all recordings


