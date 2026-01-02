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

PROS
1.Zero overhead when disabled (0 bytes in production binary)
2.Peak stack tracking (watermark - catches worst-case usage)
3.Stack painting for accurate measurement
4.Real-time heap monitoring (malloc/free tracking)
5.Stack/heap collision detection with alerts
6.Non-invasive - coexists with existing UART code
7.Visual terminal dashboard - no debugging skills needed
8.Single header file - just drop into project
9.Silent-by-default - secure, no data until handshake
10.Rate-limited to prevent CPU flooding

CONS(at this time)
1.ATmega328P only (won't work on other microcontrollers)
2.Shares UART - can't use if UART needed for other protocols
3.Fixed 9600 baud rate - must match existing UART config
4.Requires manual integration of handshake into UART handler
~10 bytes RAM overhead when enabled
5.Requires physical USB connection (no wireless)
6.Python + dependencies required for visualizer
7.Not real-time accurate (samples every ~256 loop iterations)
8.C/C++ - incompatible with Arduino Serial library
