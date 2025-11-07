import pyaudio

def list_audio_devices():
    p = pyaudio.PyAudio()

    print("\n\n")  # There might be some startup messages/warnings
    print("====== CHECKING AVAILABLE AUDIO DEVICES ======\n")

    device_count = p.get_device_count()

    for i in range(device_count):
        info = p.get_device_info_by_index(i)
        print(f"Device {i}: {info['name']}")

    print()
    if device_count == 0:
        print("FAILED\nNo audio devices found!\nPlease check your audio setup (see Readme).")
    else:
        print("SUCCESS\nAudio devices detected.\nYou should be able to use audio input/output.")

    print("\n==============================================")
if __name__ == "__main__":
    list_audio_devices()
