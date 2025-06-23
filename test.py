import socket
import sys

# --- Configuration ---
# !!! IMPORTANT: Change this to your printer's actual IP address !!!
PRINTER_IP = "10.0.0.212"
PRINTER_PORT = 3000
MESSAGE = b"M99999"
TIMEOUT = 5.0  # seconds to wait for a reply

# --- Main Script ---

# You can optionally pass the IP address as a command-line argument
if len(sys.argv) > 1:
    PRINTER_IP = sys.argv[1]
    print(f"INFO: Using IP address from command line: {PRINTER_IP}")
else:
    print(f"INFO: Using default IP: {PRINTER_IP}. To use a different one, run:")
    print(f"INFO: python {sys.argv[0]} <your_printer_ip>")

print("-" * 40)
print("Attempting to send direct message to printer...")
print(f"  - Destination: {PRINTER_IP}:{PRINTER_PORT}")
print(f"  - Message:     {MESSAGE}")
print(f"  - Timeout:     {TIMEOUT} seconds")
print("-" * 40)


# Create a UDP socket using a 'with' statement for automatic cleanup
# AF_INET is for IPv4, SOCK_DGRAM is for UDP
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    # Set a timeout on the socket for receiving data
    sock.settimeout(TIMEOUT)

    try:
        # 1. Send the message
        # No need to bind() a port; the OS assigns a temporary one automatically.
        print("STEP 1: Sending message...")
        sock.sendto(MESSAGE, (PRINTER_IP, PRINTER_PORT))
        print("       ...Message sent successfully.")

        # 2. Wait for a reply
        print("\nSTEP 2: Waiting for a reply...")
        # The buffer size (e.g., 4096) is the max data we can receive at once.
        data, addr = sock.recvfrom(4096)

        # 3. If we get here, it worked!
        print("\n✅ --- SUCCESS --- ✅")
        print(f"Received response from IP: {addr[0]}")
        print(f"Received response from Port: {addr[1]}")
        print(f"Data received (raw bytes): {data}")
        # Try to decode the response as text for readability
        print(f"Data received (decoded):   {data.decode('utf-8', errors='ignore')}")

    except socket.timeout:
        print("\n❌ --- FAILURE: TIMEOUT --- ❌")
        print(
            "The operation timed out because no response was received from the printer."
        )
        print("\nThis could mean:")
        print("  1. The IP address is wrong or the printer is offline.")
        print(
            "  2. A firewall on your computer (Windows Defender) is blocking the incoming UDP packet."
        )
        print(
            "  3. The printer is programmed to ignore direct messages and only responds to broadcasts."
        )

    except OSError as e:
        print("\n❌ --- FAILURE: OS ERROR --- ❌")
        print(f"A socket error occurred: {e}")
        print("This can happen if the IP address is unreachable (e.g., wrong subnet).")
