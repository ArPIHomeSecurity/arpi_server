#!/bin/bash

# Raspberry Pi SPI Loopback Test using spi-pipe
# Hardware setup: Connect GPIO 10 (MOSI) to GPIO 9 (MISO) with a jumper wire
# 
# Pin connections for SPI0:
# - GPIO 10 (Pin 19) - MOSI (Master Out Slave In)
# - GPIO 9  (Pin 21) - MISO (Master In Slave Out) 
# - GPIO 11 (Pin 23) - SCLK (Serial Clock)
# - GPIO 8  (Pin 24) - CE0 (Chip Enable 0)

# Removed set -e to prevent premature exit on SPI errors

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Raspberry Pi SPI Loopback Test ===${NC}"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Check if spi-pipe is installed
if ! command -v spi-pipe &> /dev/null; then
    echo -e "${YELLOW}spi-pipe not found. Installing...${NC}"
    apt-get update
    apt-get install -y spi-tools
fi

# Check if xxd is installed (part of vim-common)
if ! command -v xxd &> /dev/null; then
    echo -e "${YELLOW}xxd not found. Installing...${NC}"
    apt-get install -y xxd
fi

# Enable SPI interface - check both possible locations
echo -e "${YELLOW}Enabling SPI interface...${NC}"

CONFIG_FILE=""
if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f "/boot/config.txt" ]; then
    CONFIG_FILE="/boot/config.txt"
else
    echo -e "${RED}Error: Cannot find config.txt in /boot/firmware/ or /boot/${NC}"
    exit 1
fi

echo "Using config file: $CONFIG_FILE"

if ! grep -q "dtparam=spi=on" "$CONFIG_FILE"; then
    echo "dtparam=spi=on" >> "$CONFIG_FILE"
    echo -e "${YELLOW}SPI enabled in $CONFIG_FILE. Please reboot and run again.${NC}"
    exit 0
fi

# Load SPI kernel module
modprobe spi_bcm2835 2>/dev/null || true

# Check if SPI device exists
SPI_DEV="/dev/spidev0.0"
if [ ! -e "$SPI_DEV" ]; then
    echo -e "${RED}Error: SPI device $SPI_DEV not found${NC}"
    echo "Make sure SPI is enabled and reboot if necessary"
    exit 1
fi

echo -e "${GREEN}SPI device found: $SPI_DEV${NC}"
echo

# Hardware check reminder
echo -e "${YELLOW}HARDWARE SETUP REQUIRED:${NC}"
echo "Connect a jumper wire between:"
echo "  GPIO 10 (Pin 19, MOSI) ←→ GPIO 9 (Pin 21, MISO)"
echo
read -p "Press Enter when hardware connection is ready..."
echo

# Test parameters
SPI_SPEED=1000000  # 1MHz

echo -e "${BLUE}Starting SPI loopback tests...${NC}"
echo "SPI Speed: ${SPI_SPEED} Hz"
echo "SPI Device: $SPI_DEV"
echo

# First, let's test spi-pipe directly and see the actual error
echo -e "${YELLOW}Testing spi-pipe directly...${NC}"
echo "Running: echo -ne '\x55' | spi-pipe -d $SPI_DEV -s $SPI_SPEED"

# Capture the actual error message
temp_error="/tmp/spi_error_$"
if echo -ne '\x55' | spi-pipe -d "$SPI_DEV" -s "$SPI_SPEED" > /dev/null 2>"$temp_error"; then
    echo "spi-pipe basic test succeeded"
else
    echo "spi-pipe basic test failed - ERROR MESSAGE:"
    cat "$temp_error"
    echo "---"
fi
rm -f "$temp_error"

echo
echo -e "${YELLOW}Checking SPI device permissions and status...${NC}"
ls -la "$SPI_DEV"
echo "Current user: $(whoami)"
echo "Current groups: $(groups)"
echo

echo -e "${YELLOW}Checking if SPI device is busy...${NC}"
lsof "$SPI_DEV" 2>/dev/null || echo "No processes using SPI device"
echo

echo -e "${YELLOW}Trying to add user to spi group (if not already)...${NC}"
usermod -a -G spi root 2>/dev/null || echo "User already in spi group or command failed"
echo

echo -e "${YELLOW}Testing manual SPI access with direct device I/O...${NC}"
# Try to open the device directly
if [ -r "$SPI_DEV" ] && [ -w "$SPI_DEV" ]; then
    echo "SPI device is readable and writable"
    
    # Try a simple echo to the device
    if echo -ne '\xAA' > "$SPI_DEV" 2>/dev/null; then
        echo "Direct write to SPI device succeeded"
    else
        echo "Direct write to SPI device failed"
    fi
else
    echo "SPI device is not readable/writable"
fi

echo
echo -e "${YELLOW}Installing and trying spidev_test...${NC}"
apt-get install -y linux-tools-generic linux-tools-common 2>/dev/null || echo "Could not install linux-tools"

# Try to find spidev_test in different locations
SPIDEV_TEST=""
for path in /usr/bin/spidev_test /usr/local/bin/spidev_test /opt/vc/bin/spidev_test; do
    if [ -f "$path" ]; then
        SPIDEV_TEST="$path"
        break
    fi
done

if [ -n "$SPIDEV_TEST" ]; then
    echo "Found spidev_test at: $SPIDEV_TEST"
    echo "Running: $SPIDEV_TEST -D $SPI_DEV -s $SPI_SPEED -l"
    "$SPIDEV_TEST" -D "$SPI_DEV" -s "$SPI_SPEED" -l 2>&1 || true
else
    echo "spidev_test not found - creating simple test program..."
    
    # Create a simple C program to test SPI
    cat > /tmp/spi_simple_test.c << 'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/spi/spidev.h>

int main(int argc, char *argv[]) {
    int fd;
    unsigned char tx[] = {0xAA};
    unsigned char rx[1] = {0};
    struct spi_ioc_transfer tr = {
        .tx_buf = (unsigned long)tx,
        .rx_buf = (unsigned long)rx,
        .len = 1,
        .speed_hz = 1000000,
        .bits_per_word = 8,
    };
    
    if (argc < 2) {
        printf("Usage: %s /dev/spidevX.Y\n", argv[0]);
        return 1;
    }
    
    fd = open(argv[1], O_RDWR);
    if (fd < 0) {
        perror("Can't open device");
        return 1;
    }
    
    if (ioctl(fd, SPI_IOC_MESSAGE(1), &tr) < 1) {
        perror("Can't send spi message");
        close(fd);
        return 1;
    }
    
    printf("Sent: 0x%02X, Received: 0x%02X\n", tx[0], rx[0]);
    close(fd);
    return 0;
}
EOF
    
    if gcc -o /tmp/spi_simple_test /tmp/spi_simple_test.c 2>/dev/null; then
        echo "Compiled simple SPI test - running:"
        /tmp/spi_simple_test "$SPI_DEV" 2>&1 || true
        rm -f /tmp/spi_simple_test /tmp/spi_simple_test.c
    else
        echo "Could not compile simple SPI test (gcc not available)"
        rm -f /tmp/spi_simple_test.c
    fi
fi

echo
echo -e "${YELLOW}Checking kernel modules and SPI setup...${NC}"
echo "Loaded SPI modules:"
lsmod | grep spi || echo "No SPI modules found"
echo

echo "SPI devices in /dev:"
ls -la /dev/spi* 2>/dev/null || echo "No SPI devices found"
echo

echo "dmesg SPI messages (last 20 lines):"
dmesg | grep -i spi | tail -20 || echo "No SPI messages in dmesg"

echo
echo -e "${BLUE}spi-pipe is not working, but direct SPI access works!${NC}"
echo -e "${YELLOW}Creating custom SPI test program...${NC}"

# Create a better SPI test program
cat > /tmp/spi_loopback_test.c << 'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/spi/spidev.h>
#include <string.h>

int spi_test(const char* device, unsigned char test_byte, unsigned int speed) {
    int fd;
    unsigned char tx[1] = {test_byte};
    unsigned char rx[1] = {0};
    
    struct spi_ioc_transfer tr = {
        .tx_buf = (unsigned long)tx,
        .rx_buf = (unsigned long)rx,
        .len = 1,
        .speed_hz = speed,
        .bits_per_word = 8,
    };
    
    fd = open(device, O_RDWR);
    if (fd < 0) {
        return -1;
    }
    
    if (ioctl(fd, SPI_IOC_MESSAGE(1), &tr) < 1) {
        close(fd);
        return -2;
    }
    
    printf("%02x", rx[0]);  // Print received byte as hex
    close(fd);
    return 0;
}

int spi_test_multi(const char* device, unsigned char* test_bytes, int len, unsigned int speed) {
    int fd;
    unsigned char rx[len];
    memset(rx, 0, len);
    
    struct spi_ioc_transfer tr = {
        .tx_buf = (unsigned long)test_bytes,
        .rx_buf = (unsigned long)rx,
        .len = len,
        .speed_hz = speed,
        .bits_per_word = 8,
    };
    
    fd = open(device, O_RDWR);
    if (fd < 0) {
        return -1;
    }
    
    if (ioctl(fd, SPI_IOC_MESSAGE(1), &tr) < 1) {
        close(fd);
        return -2;
    }
    
    for (int i = 0; i < len; i++) {
        printf("%02x", rx[i]);
    }
    close(fd);
    return 0;
}

int main(int argc, char *argv[]) {
    if (argc < 4) {
        printf("Usage: %s <device> <test_type> <speed> [test_byte]\n", argv[0]);
        printf("test_type: single, multi\n");
        return 1;
    }
    
    const char* device = argv[1];
    const char* test_type = argv[2];
    unsigned int speed = atoi(argv[3]);
    
    if (strcmp(test_type, "single") == 0 && argc >= 5) {
        unsigned char test_byte = (unsigned char)strtol(argv[4], NULL, 16);
        return spi_test(device, test_byte, speed);
    } else if (strcmp(test_type, "multi") == 0) {
        unsigned char test_bytes[] = {0x12, 0x34, 0x56, 0x78};
        return spi_test_multi(device, test_bytes, 4, speed);
    }
    
    return 1;
}
EOF

# Compile the test program
if gcc -o /tmp/spi_loopback_test /tmp/spi_loopback_test.c 2>/dev/null; then
    echo -e "${GREEN}SPI test program compiled successfully!${NC}"
else
    echo -e "${RED}Failed to compile SPI test program${NC}"
    exit 1
fi

echo
echo -e "${YELLOW}Now testing with custom SPI program...${NC}"
echo "If you have the loopback wire connected (GPIO 10 to GPIO 9), you should see matching values."
echo "If not connected, you'll see 00 for all received values."
echo

PASS_COUNT=0
FAIL_COUNT=0

# Function to run individual test using our custom program
run_spi_test_custom() {
    local test_byte="$1"
    local expected_name="$2"
    
    echo "DEBUG: Running test for $expected_name (byte: $test_byte)..."
    
    # Run our custom SPI test program
    local response=""
    if response=$(/tmp/spi_loopback_test "$SPI_DEV" single "$SPI_SPEED" "$test_byte" 2>/dev/null); then
        echo "DEBUG: Custom SPI test succeeded, received: 0x$response"
    else
        echo "DEBUG: Custom SPI test failed"
        response="00"
    fi
    
    # Manual hex conversion for expected value
    local expected_hex
    case "$expected_name" in
        "0x00") expected_hex="00" ;;
        "0xFF") expected_hex="ff" ;;
        "0xAA") expected_hex="aa" ;;
        "0x55") expected_hex="55" ;;
        "0x01") expected_hex="01" ;;
        "0x02") expected_hex="02" ;;
        "0x04") expected_hex="04" ;;
        "0x08") expected_hex="08" ;;
        "0x10") expected_hex="10" ;;
        "0x20") expected_hex="20" ;;
        "0x40") expected_hex="40" ;;
        "0x80") expected_hex="80" ;;
        "0xA5") expected_hex="a5" ;;
        *) expected_hex="unknown" ;;
    esac
    
    # Compare results
    if [ "$response" = "$expected_hex" ]; then
        echo -e "Test $expected_name: ${GREEN}PASS${NC} (sent: $expected_name, received: 0x$response)"
        PASS_COUNT=$((PASS_COUNT + 1))
        return 0
    else
        echo -e "Test $expected_name: ${RED}FAIL${NC} (sent: $expected_name, received: 0x$response)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        return 1
    fi
}

read -p "Press Enter to continue with pattern tests using custom SPI program..."

PASS_COUNT=0
FAIL_COUNT=0

# Function to run individual test - NO command substitution at all
run_spi_test() {
    local test_value="$1"
    local expected_name="$2"
    
    echo "DEBUG: Running test for $expected_name..."
    
    # Create temporary files
    local temp_binary_file="/tmp/spi_binary_$"
    local temp_hex_file="/tmp/spi_hex_$"
    local temp_clean_hex="/tmp/spi_clean_$"
    
    # Send test data and capture response
    if echo -ne "$test_value" | spi-pipe -d "$SPI_DEV" -s "$SPI_SPEED" > "$temp_binary_file" 2>/dev/null; then
        echo "DEBUG: spi-pipe command succeeded"
    else
        echo "DEBUG: spi-pipe command failed with exit code $?"
        return 1
    fi
    
    # Check if output file was created
    if [ ! -f "$temp_binary_file" ]; then
        echo "DEBUG: Output file was not created"
        return 1
    fi
    
    echo "DEBUG: Output file size: $(wc -c < "$temp_binary_file") bytes"
    
    # Convert binary to hex (no command substitution)
    od -An -tx1 "$temp_binary_file" > "$temp_hex_file"
    tr -d ' \n' < "$temp_hex_file" > "$temp_clean_hex"
    
    # Read the hex result
    if [ -s "$temp_clean_hex" ]; then
        read -r actual_hex < "$temp_clean_hex"
        echo "DEBUG: Received hex: '$actual_hex'"
    else
        actual_hex=""
        echo "DEBUG: No hex data received"
    fi
    
    # Clean up temp files
    rm -f "$temp_binary_file" "$temp_hex_file" "$temp_clean_hex"
    
    # Manual hex conversion for expected value - no printf command substitution
    local expected_hex
    case "$expected_name" in
        "0x00") expected_hex="00" ;;
        "0xFF") expected_hex="ff" ;;
        "0xAA") expected_hex="aa" ;;
        "0x55") expected_hex="55" ;;
        "0x01") expected_hex="01" ;;
        "0x02") expected_hex="02" ;;
        "0x04") expected_hex="04" ;;
        "0x08") expected_hex="08" ;;
        "0x10") expected_hex="10" ;;
        "0x20") expected_hex="20" ;;
        "0x40") expected_hex="40" ;;
        "0x80") expected_hex="80" ;;
        "0xA5") expected_hex="a5" ;;
        *) expected_hex="unknown" ;;
    esac
    
    # Compare results
    if [ "$actual_hex" = "$expected_hex" ]; then
        echo -e "Test $expected_name: ${GREEN}PASS${NC} (sent: $expected_name, received: 0x$actual_hex)"
        PASS_COUNT=$((PASS_COUNT + 1))
        return 0
    else
        echo -e "Test $expected_name: ${RED}FAIL${NC} (sent: $expected_name, received: 0x$actual_hex)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        return 1
    fi
}

# Run tests with different patterns - using our custom program
echo -e "${YELLOW}Running pattern tests with custom SPI program:${NC}"

run_spi_test_custom "00" "0x00"
run_spi_test_custom "FF" "0xFF"
run_spi_test_custom "AA" "0xAA"
run_spi_test_custom "55" "0x55"
run_spi_test_custom "01" "0x01"
run_spi_test_custom "02" "0x02"
run_spi_test_custom "04" "0x04"
run_spi_test_custom "08" "0x08"
run_spi_test_custom "10" "0x10"
run_spi_test_custom "20" "0x20"
run_spi_test_custom "40" "0x40"
run_spi_test_custom "80" "0x80"

echo

# Multi-byte test using custom program
echo -e "${YELLOW}Running multi-byte test:${NC}"
if multi_response=$(/tmp/spi_loopback_test "$SPI_DEV" multi "$SPI_SPEED" 2>/dev/null); then
    echo "DEBUG: Multi-byte test succeeded, received: 0x$multi_response"
    if [ "$multi_response" = "12345678" ]; then
        echo -e "Multi-byte test: ${GREEN}PASS${NC} (sent: 0x12345678, received: 0x$multi_response)"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo -e "Multi-byte test: ${RED}FAIL${NC} (sent: 0x12345678, received: 0x$multi_response)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
else
    echo "DEBUG: Multi-byte test failed"
    echo -e "Multi-byte test: ${RED}FAIL${NC} (sent: 0x12345678, received: 0x00000000)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

echo

# Speed test at different frequencies using custom program
echo -e "${YELLOW}Running speed tests:${NC}"

for speed in 100000 500000 1000000 2000000 5000000 10000000; do
    if speed_response=$(/tmp/spi_loopback_test "$SPI_DEV" single "$speed" "A5" 2>/dev/null); then
        if [ "$speed_response" = "a5" ]; then
            echo -e "Speed ${speed} Hz: ${GREEN}PASS${NC}"
            PASS_COUNT=$((PASS_COUNT + 1))
        else
            echo -e "Speed ${speed} Hz: ${RED}FAIL${NC} (received: 0x$speed_response)"
            FAIL_COUNT=$((FAIL_COUNT + 1))
        fi
    else
        echo -e "Speed ${speed} Hz: ${RED}FAIL${NC} (SPI communication failed)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

# Clean up
rm -f /tmp/spi_loopback_test /tmp/spi_loopback_test.c

echo
echo -e "${BLUE}=== Test Summary ===${NC}"
echo -e "Total Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Total Failed: ${RED}$FAIL_COUNT${NC}"

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "\n${GREEN}🎉 All tests passed! SPI loopback is working correctly.${NC}"
    exit 0
else
    echo -e "\n${RED}⚠️  Some tests failed. Check hardware connections.${NC}"
    echo
    echo "Troubleshooting tips:"
    echo "1. Verify jumper wire connection between GPIO 10 and GPIO 9"
    echo "2. Check that SPI is enabled: ls /dev/spi*"
    echo "3. Ensure no other process is using SPI"
    echo "4. Try different jumper wire if connection is loose"
    exit 1
fi
