"""Create an original, local audio fixture without a music service or credentials."""
import math
import struct
import wave
from pathlib import Path

output = Path(__file__).resolve().parents[1] / 'backend' / 'static' / 'assets' / 'demo-chimes.wav'
rate = 22050
notes = [261.63, 329.63, 392.00, 493.88, 440.00, 392.00, 329.63, 293.66]
duration = 24
with wave.open(str(output), 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(rate)
    data = bytearray()
    for sample in range(duration * rate):
        time = sample / rate
        value = 0
        for index, frequency in enumerate(notes * 2):
            age = time - index * 1.35
            if 0 <= age < 5:
                envelope = min(1, age / .04) * math.exp(-age * 1.1)
                value += envelope * (math.sin(2 * math.pi * frequency * age) + .18 * math.sin(2 * math.pi * frequency * 2 * age)) * .18
        fade = min(1, max(0, (duration - time) / 3))
        data.extend(struct.pack('<h', int(max(-1, min(1, value * fade)) * 32767)))
    wav.writeframes(data)
print(output)
