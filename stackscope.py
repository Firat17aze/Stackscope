#!/usr/bin/env python3
"""StackScope - Real-time memory visualizer for ATmega328P"""

import serial
import serial.tools.list_ports
import argparse
import sys
import time
from typing import Optional, List, Tuple
from collections import deque
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.table import Table

# Protocol
HANDSHAKE_BYTE = 0xA5
HEADER_BYTE = 0xFE
TOTAL_SRAM = 2048

FLAG_ALERT = 0x01
FLAG_COLLISION = 0x02
FLAG_PEAK_NEW = 0x04
FLAG_HEAP_ACTIVE = 0x08

PACKET_V1_SIZE = 3
PACKET_V2_SIZE = 10
HISTORY_SIZE = 60
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT = 0.5


class StackScopeVisualizer:
    def __init__(self, port: Optional[str] = None, baud: int = DEFAULT_BAUD, 
                 static_data: int = 0):
        self.port = port
        self.baud = baud
        self.static_data = static_data
        self.serial_conn: Optional[serial.Serial] = None
        self.console = Console()
        
        self.stack_usage = 0
        self.peak_usage = 0
        self.heap_usage = 0
        self.free_memory = TOTAL_SRAM
        self.flags = 0
        
        self.packet_count = 0
        self.last_update = time.time()
        self.start_time = time.time()
        
        self.stack_history: deque = deque(maxlen=HISTORY_SIZE)
        self.heap_history: deque = deque(maxlen=HISTORY_SIZE)
        
        self.collision_detected = False
        self.alert_active = False
        self.peak_flash = False
        
    def find_serial_port(self) -> Optional[str]:
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.console.print("[red]No serial ports found![/red]")
            return None
        
        # Look for Arduino-like devices
        arduino_ports = [p for p in ports if 'Arduino' in p.description or 'CH340' in p.description or 'USB' in p.description]
        
        if len(arduino_ports) == 1:
            return arduino_ports[0].device
        
        if len(ports) == 1:
            return ports[0].device
        
        self.console.print("[yellow]Multiple ports found:[/yellow]")
        for i, port in enumerate(ports, 1):
            self.console.print(f"  {i}. {port.device} - {port.description}")
        
        try:
            choice = input("\nSelect port number: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx].device
        except (ValueError, KeyboardInterrupt):
            pass
        
        return None
    
    def connect(self) -> bool:
        if not self.port:
            self.port = self.find_serial_port()
            if not self.port:
                return False
        
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=DEFAULT_TIMEOUT,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            
            time.sleep(2.0)  # wait for Arduino reset
            self.serial_conn.reset_input_buffer()
            for _ in range(3):
                self.serial_conn.write(bytes([HANDSHAKE_BYTE]))
                time.sleep(0.1)
            
            self.console.print(f"[green]Connected to {self.port}[/green]")
            self.console.print("[cyan]Handshake sent - waiting for data...[/cyan]")
            self.start_time = time.time()
            return True
            
        except serial.SerialException as e:
            self.console.print(f"[red]Failed to connect: {e}[/red]")
            return False
    
    def disconnect(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
    
    def read_word(self) -> int:
        data = self.serial_conn.read(2)
        if len(data) == 2:
            return (data[0] << 8) | data[1]
        return 0
    
    def read_packet(self) -> bool:
        if not self.serial_conn or not self.serial_conn.is_open:
            return False
        
        while self.serial_conn.in_waiting >= PACKET_V1_SIZE:
            byte = self.serial_conn.read(1)
            if not byte or byte[0] != HEADER_BYTE:
                continue
            
            next_byte = self.serial_conn.read(1)
            if not next_byte:
                continue
            
            flags_or_high = next_byte[0]
            
            # v2 packet?
            if self.serial_conn.in_waiting >= (PACKET_V2_SIZE - 2) and flags_or_high < 0x10:
                self.flags = flags_or_high
                self.stack_usage = self.read_word()
                self.peak_usage = self.read_word()
                self.heap_usage = self.read_word()
                self.free_memory = self.read_word()
            else:
                # v1 fallback
                low_byte = self.serial_conn.read(1)
                if low_byte:
                    self.stack_usage = (flags_or_high << 8) | low_byte[0]
                    self.peak_usage = max(self.peak_usage, self.stack_usage)
                    self.free_memory = TOTAL_SRAM - self.static_data - self.stack_usage
                    self.flags = 0
                    self.heap_usage = 0
            
            self.alert_active = bool(self.flags & FLAG_ALERT)
            self.collision_detected = bool(self.flags & FLAG_COLLISION)
            self.peak_flash = bool(self.flags & FLAG_PEAK_NEW)
            self.stack_history.append(self.stack_usage)
            self.heap_history.append(self.heap_usage)
            
            self.packet_count += 1
            self.last_update = time.time()
            return True
        
        return False
    
    def make_bar(self, value: int, max_val: int, width: int, color: str, 
                 show_marker: bool = False, marker_pos: int = 0) -> str:
        if max_val == 0:
            pct = 0
        else:
            pct = min(value / max_val, 1.0)
        
        filled = int(pct * width)
        bar = '█' * filled + '░' * (width - filled)
        
        # Add peak marker if requested
        if show_marker and marker_pos > 0:
            marker_idx = int(min(marker_pos / max_val, 1.0) * width)
            if marker_idx < width:
                bar = bar[:marker_idx] + '▌' + bar[marker_idx+1:]
        
        return f"[{color}]{bar}[/{color}]"
    
    def make_sparkline(self, history: deque, max_val: int) -> str:
        if not history or max_val == 0:
            return "─" * 20
        
        blocks = " ▁▂▃▄▅▆▇█"
        line = ""
        samples = list(history)[-20:] if len(history) > 20 else list(history)
        
        for val in samples:
            idx = min(int(val / max_val * 8), 8)
            line += blocks[idx]
        
        line += "─" * (20 - len(samples))
        return line
    
    def create_dashboard(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", size=18),
            Layout(name="alerts", size=4),
            Layout(name="footer", size=3)
        )
        
        header_text = Text()
        header_text.append("StackScope v2.0", style="bold cyan")
        header_text.append(" │ ", style="dim")
        header_text.append(f"Port: {self.port or 'N/A'}", style="dim")
        header_text.append(" │ ", style="dim")
        header_text.append(f"Packets: {self.packet_count}", style="dim green")
        
        if self.packet_count > 0:
            elapsed = time.time() - self.last_update
            if elapsed < 2:
                header_text.append(" │ ", style="dim")
                header_text.append("● LIVE", style="bold green")
            else:
                header_text.append(" │ ", style="dim")
                header_text.append("○ STALE", style="yellow")
        
        layout["header"].update(Panel(Align.center(header_text), border_style="cyan"))
        
        main_layout = Layout()
        main_layout.split_row(
            Layout(name="bars", ratio=2),
            Layout(name="graphs", ratio=1)
        )
        
        bar_table = Table(show_header=False, box=None, padding=(0, 1))
        bar_table.add_column("Label", width=14)
        bar_table.add_column("Value", width=14)
        bar_table.add_column("Bar", width=25)
        
        static_pct = (self.static_data / TOTAL_SRAM) * 100
        bar_table.add_row(
            "[blue]Static Data[/blue]",
            f"{self.static_data:4d}B ({static_pct:4.1f}%)",
            self.make_bar(self.static_data, TOTAL_SRAM, 20, "blue")
        )
        
        stack_pct = (self.stack_usage / TOTAL_SRAM) * 100
        stack_color = "red" if self.alert_active else "yellow"
        bar_table.add_row(
            f"[{stack_color}]Stack Usage[/{stack_color}]",
            f"{self.stack_usage:4d}B ({stack_pct:4.1f}%)",
            self.make_bar(self.stack_usage, TOTAL_SRAM, 20, stack_color, True, self.peak_usage)
        )
        
        peak_pct = (self.peak_usage / TOTAL_SRAM) * 100
        peak_style = "bold red" if self.peak_flash else "red"
        bar_table.add_row(
            f"[{peak_style}]Peak Stack[/{peak_style}]",
            f"{self.peak_usage:4d}B ({peak_pct:4.1f}%)",
            self.make_bar(self.peak_usage, TOTAL_SRAM, 20, "red")
        )
        
        heap_pct = (self.heap_usage / TOTAL_SRAM) * 100
        heap_color = "magenta" if self.heap_usage > 0 else "dim"
        bar_table.add_row(
            f"[{heap_color}]Heap Usage[/{heap_color}]",
            f"{self.heap_usage:4d}B ({heap_pct:4.1f}%)",
            self.make_bar(self.heap_usage, TOTAL_SRAM, 20, heap_color)
        )
        
        free_pct = (self.free_memory / TOTAL_SRAM) * 100
        free_color = "red" if self.free_memory < 50 else "green"
        bar_table.add_row(
            f"[{free_color}]Free Memory[/{free_color}]",
            f"{self.free_memory:4d}B ({free_pct:4.1f}%)",
            self.make_bar(self.free_memory, TOTAL_SRAM, 20, free_color)
        )
        
        used = self.static_data + self.stack_usage + self.heap_usage
        used_pct = (used / TOTAL_SRAM) * 100
        bar_table.add_row("", "", "")
        bar_table.add_row(
            "[white]Total Used[/white]",
            f"{used:4d}B ({used_pct:4.1f}%)",
            self.make_bar(used, TOTAL_SRAM, 20, "white")
        )
        
        bar_panel = Panel(bar_table, title="Memory Usage", border_style="blue")
        main_layout["bars"].update(bar_panel)
        
        graph_text = Text()
        graph_text.append("Stack History:\n", style="yellow")
        graph_text.append(self.make_sparkline(self.stack_history, 500))
        graph_text.append("\n\n")
        graph_text.append("Heap History:\n", style="magenta")
        graph_text.append(self.make_sparkline(self.heap_history, 500))
        graph_text.append("\n\n")
        graph_text.append(f"Runtime: {time.time() - self.start_time:.0f}s\n", style="dim")
        graph_text.append(f"Update: {1/(max(0.1, time.time()-self.last_update)):.1f}Hz", style="dim")
        
        graph_panel = Panel(graph_text, title="History", border_style="dim")
        main_layout["graphs"].update(graph_panel)
        
        layout["main"].update(main_layout)
        
        alert_text = Text()
        if self.collision_detected:
            alert_text.append("⚠ CRITICAL: STACK/HEAP COLLISION DETECTED! ", style="bold red on white")
        elif self.alert_active:
            alert_text.append("⚠ WARNING: Free memory below 50 bytes! ", style="bold yellow")
        elif self.peak_flash:
            alert_text.append("↑ New peak stack usage recorded ", style="cyan")
        else:
            alert_text.append("✓ Memory status: OK ", style="green")
        
        alert_text.append("\n\n")
        alert_text.append("Memory Map: ", style="dim")
        alert_text.append("[", style="dim")
        alert_text.append("STATIC", style="blue")
        alert_text.append("|", style="dim")
        alert_text.append("HEAP→", style="magenta")
        alert_text.append("···FREE···", style="green")
        alert_text.append("←STACK", style="yellow")
        alert_text.append("]", style="dim")
        
        alert_color = "red" if self.collision_detected else ("yellow" if self.alert_active else "green")
        layout["alerts"].update(Panel(Align.center(alert_text), title="Status", border_style=alert_color))
        
        footer_text = Text("Ctrl+C to exit", style="dim")
        layout["footer"].update(Panel(Align.center(footer_text), border_style="dim"))
        
        return layout
    
    def run(self):
        if not self.connect():
            return
        
        last_handshake = time.time()
        
        try:
            with Live(self.create_dashboard(), refresh_per_second=10, screen=True) as live:
                while True:
                    while self.read_packet():
                        pass
                    
                    if self.packet_count == 0 and (time.time() - last_handshake) > 2.0:
                        self.serial_conn.write(bytes([HANDSHAKE_BYTE]))
                        last_handshake = time.time()
                    
                    live.update(self.create_dashboard())
                    time.sleep(0.05)
                    
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Interrupted by user[/yellow]")
        finally:
            self.disconnect()
            self.console.print(f"[dim]Total packets received: {self.packet_count}[/dim]")
            self.console.print(f"[dim]Peak stack usage: {self.peak_usage} bytes[/dim]")


def main():
    parser = argparse.ArgumentParser(description="StackScope - Memory profiler for ATmega328P")
    
    parser.add_argument('--port', '-p', type=str, default=None,
                        help='Serial port (auto-detect if not specified)')
    parser.add_argument('--baud', '-b', type=int, default=DEFAULT_BAUD,
                        help=f'Baud rate (default: {DEFAULT_BAUD})')
    parser.add_argument('--static-data', '-s', type=int, default=0,
                        help='Static data usage in bytes (from compiler output)')
    
    args = parser.parse_args()
    
    visualizer = StackScopeVisualizer(
        port=args.port,
        baud=args.baud,
        static_data=args.static_data
    )
    
    visualizer.run()


if __name__ == "__main__":
    main()
