#!/bin/bash

# MCP3008 ADC Reader for Raspberry Pi Zero Bookworm
# Hardware connections:
# MCP3008 VDD  -> 5V   (Pin 2 or 4)
# MCP3008 VREF -> 5V   (Pin 2 or 4) 
# MCP3008 AGND -> GND  (Pin 14)
# MCP3008 DGND -> GND  (Pin 9)
# MCP3008 CLK  -> GPIO 11 (SCLK, Pin 23)
# MCP3008 DOUT -> GPIO 9  (MISO, Pin 21)
# MCP3008 DIN  -> GPIO 10 (MOSI, Pin 19)
# MCP3008 CS   -> GPIO 8  (CE0, Pin 24)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== MCP3008 ADC Reader for Raspberry Pi ===${NC}"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -c, --channel <0-7>     Read single channel (0-7)"
    echo "  -a, --all              Read all 8 channels"
    echo "  -m, --monitor          Monitor mode (continuous reading)"
    echo "  -d, --device <device>   SPI device (default: /dev/spidev0.0)"
    echo "  -s, --speed <speed>     SPI speed in Hz (default: 1000000)"
    echo "  -v, --voltage          Show voltage (assuming 5V reference)
  -r, --reference <ref>  Reference voltage (default: 5.0V)"
    echo "  -r, --raw              Show raw ADC values only"
    echo "  -h, --help             Show this help"
    echo
    echo "Examples:"
    echo "  $0 -c 0              # Read channel 0 once"
    echo "  $0 -a -v             # Read all channels with voltage (5V ref)"
    echo "  $0 -c 0 -m           # Monitor channel 0 continuously"
    echo "  $0 -a -m -v          # Monitor all channels with voltage"
    echo "  $0 -c 0 -v -r 3.3    # Read channel 0 with 3.3V reference"
}

# Default values
CHANNEL=""
READ_ALL=0
MONITOR_MODE=0
SPI_DEVICE="/dev/spidev0.0"
SPI_SPEED=1000000
SHOW_VOLTAGE=0
RAW_ONLY=0
VREF=5.0

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--channel)
            CHANNEL="$2"
            if ! [[ "$CHANNEL" =~ ^[0-7]$ ]]; then
                echo -e "${RED}Error: Channel must be 0-7${NC}"
                exit 1
            fi
            shift 2
            ;;
        -a|--all)
            READ_ALL=1
            shift
            ;;
        -m|--monitor)
            MONITOR_MODE=1
            shift
            ;;
        -d|--device)
            SPI_DEVICE="$2"
            shift 2
            ;;
        -s|--speed)
            SPI_SPEED="$2"
            shift 2
            ;;
        -r|--reference)
            VREF="$2"
            if ! [[ "$VREF" =~ ^[0-9]+\.?[0-9]*$ ]]; then
                echo -e "${RED}Error: Reference voltage must be a number${NC}"
                exit 1
            fi
            shift 2
            ;;
        -v|--voltage)
            SHOW_VOLTAGE=1
            shift
            ;;
        -r|--raw)
            RAW_ONLY=1
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_usage
            exit 1
            ;;
    esac
done

# Validate arguments
if [ "$READ_ALL" -eq 0 ] && [ -z "$CHANNEL" ]; then
    echo -e "${RED}Error: Must specify either -c <channel> or -a (all channels)${NC}"
    show_usage
    exit 1
fi

# Check if SPI device exists
if [ ! -e "$SPI_DEVICE" ]; then
    echo -e "${RED}Error: SPI device $SPI_DEVICE not found${NC}"
    echo "Make sure SPI is enabled: sudo raspi-config -> Interface Options -> SPI"
    exit 1
fi

echo -e "${GREEN}SPI device: $SPI_DEVICE${NC}"
echo -e "${GREEN}SPI speed: $SPI_SPEED Hz${NC}"
echo -e "${GREEN}Reference voltage: ${VREF}V${NC}"
echo

# Create MCP3008 reader C program
cat > /tmp/mcp3008_reader.c << 'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/spi/spidev.h>

int read_mcp3008_channel(const char* device, int channel, unsigned int speed) {
    int fd;
    unsigned char tx[3], rx[3];
    
    // MCP3008 command structure:
    // Byte 1: Start bit (1) + Single/Diff (1) + Channel (3 bits) + padding
    // Byte 2: padding
    // Byte 3: padding
    // Response comes in bytes 2 and 3 (10 bits total)
    
    tx[0] = 0x01;  // Start bit
    tx[1] = (0x08 | channel) << 4;  // Single-ended mode + channel select
    tx[2] = 0x00;  // Don't care
    
    rx[0] = 0;
    rx[1] = 0; 
    rx[2] = 0;
    
    struct spi_ioc_transfer tr = {
        .tx_buf = (unsigned long)tx,
        .rx_buf = (unsigned long)rx,
        .len = 3,
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
    
    close(fd);
    
    // Extract 10-bit result from rx[1] and rx[2]
    int result = ((rx[1] & 0x03) << 8) | rx[2];
    return result;
}

int main(int argc, char *argv[]) {
    if (argc != 4) {
        printf("Usage: %s <device> <channel> <speed>\n", argv[0]);
        return 1;
    }
    
    const char* device = argv[1];
    int channel = atoi(argv[2]);
    unsigned int speed = atoi(argv[3]);
    
    if (channel < 0 || channel > 7) {
        printf("Error: Channel must be 0-7\n");
        return 1;
    }
    
    int result = read_mcp3008_channel(device, channel, speed);
    
    if (result < 0) {
        printf("Error: SPI communication failed\n");
        return 1;
    }
    
    printf("%d\n", result);
    return 0;
}
EOF

# Compile the MCP3008 reader
if ! gcc -o /tmp/mcp3008_reader /tmp/mcp3008_reader.c 2>/dev/null; then
    echo -e "${RED}Error: Failed to compile MCP3008 reader${NC}"
    echo "Make sure gcc is installed: sudo apt install build-essential"
    exit 1
fi

echo -e "${GREEN}MCP3008 reader compiled successfully${NC}"
echo

# Function to read single channel
read_channel() {
    local channel=$1
    local result
    
    if result=$(/tmp/mcp3008_reader "$SPI_DEVICE" "$channel" "$SPI_SPEED" 2>/dev/null); then
        if [ "$RAW_ONLY" -eq 1 ]; then
            echo "$result"
        else
            printf "Channel %d: %4d" "$channel" "$result"
            if [ "$SHOW_VOLTAGE" -eq 1 ]; then
                # Calculate voltage (10-bit ADC: 0-1023 = 0V to VREF)
                voltage=$(echo "scale=3; $result * $VREF / 1023" | bc -l 2>/dev/null || echo "?.???")
                printf " (%s V)" "$voltage"
            fi
            echo
        fi
        return 0
    else
        if [ "$RAW_ONLY" -eq 0 ]; then
            echo -e "Channel $channel: ${RED}ERROR${NC}"
        fi
        return 1
    fi
}

# Function to read all channels
read_all_channels() {
    local success=0
    for ch in {0..7}; do
        if read_channel "$ch"; then
            success=$((success + 1))
        fi
    done
    
    if [ "$RAW_ONLY" -eq 0 ] && [ "$success" -gt 0 ]; then
        echo "Successfully read $success/8 channels"
    fi
}

# Install bc for voltage calculations if needed and requested
if [ "$SHOW_VOLTAGE" -eq 1 ] && ! command -v bc &> /dev/null; then
    echo -e "${YELLOW}Installing bc for voltage calculations...${NC}"
    apt-get update -qq && apt-get install -y bc -qq 2>/dev/null || echo "Warning: Could not install bc"
fi

# Main execution
if [ "$MONITOR_MODE" -eq 1 ]; then
    echo -e "${YELLOW}Monitor mode - Press Ctrl+C to stop${NC}"
    echo
    
    # Setup trap to clean up on exit
    trap 'echo -e "\n${YELLOW}Monitoring stopped${NC}"; rm -f /tmp/mcp3008_reader /tmp/mcp3008_reader.c; exit 0' INT TERM
    
    while true; do
        if [ "$RAW_ONLY" -eq 0 ]; then
            echo -n "$(date '+%H:%M:%S') - "
        fi
        
        if [ "$READ_ALL" -eq 1 ]; then
            read_all_channels
        else
            read_channel "$CHANNEL"
        fi
        
        sleep 1
    done
else
    # Single reading
    if [ "$READ_ALL" -eq 1 ]; then
        read_all_channels
    else
        read_channel "$CHANNEL"
    fi
fi

# Cleanup
rm -f /tmp/mcp3008_reader /tmp/mcp3008_reader.c
