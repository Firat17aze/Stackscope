/*
 * StackScope.h - Memory profiler for ATmega328P
 * 
 * 1. #define ENABLE_STACKSCOPE before including this
 * 2. Call StackScope_Init() after Serial.begin()
 * 3. Call StackScope_Check() in your loop
 * 4. Handle handshake in serial receive
 */

#ifndef STACKSCOPE_H
#define STACKSCOPE_H

#ifdef ENABLE_STACKSCOPE

#include <stdint.h>
#include <avr/io.h>

#define STACKSCOPE_HEADER       0xFE
#define STACKSCOPE_HANDSHAKE    0xA5
#define STACKSCOPE_VERSION      0x02

#ifndef STACKSCOPE_RATE_LIMIT
#define STACKSCOPE_RATE_LIMIT   256
#endif

#ifndef STACKSCOPE_ALERT_THRESHOLD
#define STACKSCOPE_ALERT_THRESHOLD  50
#endif

#define STACKSCOPE_PAINT_PATTERN    0xAA
#define STACKSCOPE_RAMSTART         0x0100
#define STACKSCOPE_RAMSIZE          2048

#define STACKSCOPE_FLAG_ALERT       (1 << 0)
#define STACKSCOPE_FLAG_COLLISION   (1 << 1)
#define STACKSCOPE_FLAG_PEAK_NEW    (1 << 2)
#define STACKSCOPE_FLAG_HEAP_ACTIVE (1 << 3)

extern uint8_t __heap_start;
extern uint8_t *__brkval;

static volatile uint8_t  stackscope_enabled = 0;
static volatile uint16_t stackscope_call_counter = 0;
static volatile uint16_t stackscope_peak_usage = 0;
static volatile uint16_t stackscope_painted_end = 0;

static inline uint16_t StackScope_GetSP(void) {
    uint16_t sp;
    __asm__ __volatile__ (
        "in %A0, 0x3D\n\t"
        "in %B0, 0x3E\n\t"
        : "=r" (sp)
    );
    return sp;
}

static inline uint16_t StackScope_GetHeapUsage(void) {
    if (__brkval == 0) return 0;
    return (uint16_t)__brkval - (uint16_t)&__heap_start;
}

static inline uint16_t StackScope_GetHeapEnd(void) {
    if (__brkval == 0) return (uint16_t)&__heap_start;
    return (uint16_t)__brkval;
}

static inline void StackScope_PaintStack(void) {
    uint16_t sp = StackScope_GetSP();
    uint16_t heap_end = StackScope_GetHeapEnd();
    uint8_t *paint_start = (uint8_t *)heap_end;
    uint8_t *paint_end = (uint8_t *)(sp - 32);
    
    if (paint_end > paint_start) {
        for (uint8_t *p = paint_start; p < paint_end; p++) {
            *p = STACKSCOPE_PAINT_PATTERN;
        }
        stackscope_painted_end = (uint16_t)paint_end;
    }
}

static inline uint16_t StackScope_GetPaintedUsage(void) {
    if (stackscope_painted_end == 0) {
        return RAMEND - StackScope_GetSP();
    }
    
    uint8_t *scan = (uint8_t *)stackscope_painted_end;
    while (scan > (uint8_t *)StackScope_GetHeapEnd()) {
        if (*scan != STACKSCOPE_PAINT_PATTERN) {
            break;
        }
        scan--;
    }
    
    return RAMEND - (uint16_t)scan;
}

static inline void StackScope_WaitTX(void) {
    while (!(UCSR0A & (1 << UDRE0)));
}

static inline void StackScope_SendByte(uint8_t data) {
    StackScope_WaitTX();
    UDR0 = data;
}

static inline void StackScope_SendWord(uint16_t data) {
    StackScope_SendByte((uint8_t)(data >> 8));
    StackScope_SendByte((uint8_t)(data & 0xFF));
}

static inline void StackScope_Init(void) {
    stackscope_enabled = 0;
    stackscope_call_counter = 0;
    stackscope_peak_usage = 0;
    StackScope_PaintStack();
}

static inline uint8_t StackScope_IsHandshakeByte(uint8_t byte) {
    return (byte == STACKSCOPE_HANDSHAKE) ? 1 : 0;
}

static inline void StackScope_TriggerHandshake(void) {
    stackscope_enabled = 1;
    StackScope_PaintStack();
}

static inline uint16_t StackScope_GetPeak(void) {
    return stackscope_peak_usage;
}

static inline void StackScope_ResetPeak(void) {
    stackscope_peak_usage = 0;
}

static inline void StackScope_Check(void) {
    if (!stackscope_enabled) {
        return;
    }
    
    stackscope_call_counter++;
    if ((stackscope_call_counter & (STACKSCOPE_RATE_LIMIT - 1)) != 0) {
        return;
    }
    
    uint16_t stack_usage = StackScope_GetPaintedUsage();
    uint16_t heap_usage = StackScope_GetHeapUsage();
    uint16_t heap_end = StackScope_GetHeapEnd();
    uint16_t sp = StackScope_GetSP();
    uint16_t free_memory = (sp > heap_end) ? (sp - heap_end) : 0;
    uint8_t flags = 0;
    
    if (stack_usage > stackscope_peak_usage) {
        stackscope_peak_usage = stack_usage;
        flags |= STACKSCOPE_FLAG_PEAK_NEW;
    }
    
    if (free_memory < STACKSCOPE_ALERT_THRESHOLD)
        flags |= STACKSCOPE_FLAG_ALERT;
    
    if (sp <= heap_end + 16)
        flags |= STACKSCOPE_FLAG_COLLISION;
    
    if (heap_usage > 0)
        flags |= STACKSCOPE_FLAG_HEAP_ACTIVE;
    
    StackScope_SendByte(STACKSCOPE_HEADER);
    StackScope_SendByte(flags);
    StackScope_SendWord(stack_usage);
    StackScope_SendWord(stackscope_peak_usage);
    StackScope_SendWord(heap_usage);
    StackScope_SendWord(free_memory);
}

#else /* Disabled - no overhead */

#define StackScope_Init()               ((void)0)
#define StackScope_Check()              ((void)0)
#define StackScope_TriggerHandshake()   ((void)0)
#define StackScope_IsHandshakeByte(x)   (0)
#define StackScope_GetPeak()            (0)
#define StackScope_ResetPeak()          ((void)0)

#endif /* ENABLE_STACKSCOPE */

#endif /* STACKSCOPE_H */
