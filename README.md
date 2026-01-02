# StackScope 

A lightweight memory profiler for ATmega328P. 

## What it does

- Shows stack/heap usage live on your PC
- Catches stack overflows before they crash your code
- Zero cost when disabled - your production binary stays clean

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Add to your code**
```c
#define ENABLE_STACKSCOPE
#include "StackScope.h"

int main(void) {
    UART_Init();  // your UART setup first
    StackScope_Init();
    
    while (1) {
        StackScope_Check();
        // your code... 
    }
}

// In your UART RX interrupt: 
ISR(USART_RX_vect) {
    uint8_t ch = UDR0;
    if (StackScope_IsHandshakeByte(ch)) {
        StackScope_TriggerHandshake();
        return;
    }
    // handle other bytes... 
}
```

**3. Run the visualizer**
```bash
python stackscope.py --port COM5 --static-data 761
```

## Works with

Arduino Uno, Nano, Pro Mini (ATmega328P)

## Disabling for production

Just comment out `#define ENABLE_STACKSCOPE` - the profiler compiles to nothing. 

## Pros & Cons

### ✅ Pros

- **Zero overhead when disabled** - 0 bytes in production binary
- **Peak stack tracking** - Watermark catches worst-case usage
- **Stack painting** - Accurate measurement of actual usage
- **Real-time heap monitoring** - Tracks malloc/free operations
- **Collision detection** - Alerts when stack/heap boundaries clash
- **Non-invasive** - Coexists with existing UART code
- **Visual dashboard** - Terminal UI, no debugging skills needed
- **Single header file** - Drop-in integration
- **Secure by default** - Silent until handshake initiated
- **Rate-limited** - Prevents CPU flooding

### ⚠️ Cons

- **Platform-specific** - ATmega328P only
- **UART dependency** - Shares UART with your application
- **Fixed baud rate** - 9600 baud (must match your config)
- **Manual integration** - Requires handshake in UART ISR
- **RAM overhead** - ~10 bytes when enabled
- **Wired connection** - Requires physical USB cable
- **Python dependency** - Visualizer needs Python + libraries
- **Sampling rate** - Updates every ~256 loop iterations
- **C/C++ only** - Incompatible with Arduino Serial library
