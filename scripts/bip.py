import math, wave, struct, tempfile, os

f = 440       # fréquence Hz
dur = 0.4     # durée secondes
sr = 44100    # sample rate

samples = [int(32767 * math.sin(2 * math.pi * f * t / sr)) for t in range(int(sr * dur))]
data = struct.pack('<' + 'h' * len(samples), *samples)

tmp = tempfile.mktemp(suffix='.wav')
w = wave.open(tmp, 'w')
w.setnchannels(1)
w.setsampwidth(2)
w.setframerate(sr)
w.writeframes(data)
w.close()

os.system(f'aplay {tmp} 2>/dev/null')
os.remove(tmp)
