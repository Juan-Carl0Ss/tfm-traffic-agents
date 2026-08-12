"""merge_pcap.py — Merge two .pcapng captures with continuous timestamps.

The second capture's timestamps are shifted so that its first packet
follows immediately after the last packet of the first capture,
with a configurable gap (default: 1 ms).
"""

import logging
import argparse
from pathlib import Path

from scapy.all import PcapNgReader, PcapNgWriter, Packet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_GAP_SECONDS: float = 0.001  # 1 ms between last pkt of cap1 and first of cap2


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def read_packets(path: Path) -> list[Packet]:
    """Reads all packets from a .pcapng file.

    Args:
        path: Path to the input .pcapng file.

    Returns:
        List of scapy Packet objects with their original timestamps.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Capture file not found: {path}")

    logger.info("Reading packets from: %s", path)
    packets: list[Packet] = []

    with PcapNgReader(str(path)) as reader:
        for pkt in reader:
            packets.append(pkt)

    logger.info("  -> %d packets read", len(packets))
    return packets


def shift_timestamps(packets: list[Packet], offset: float) -> list[Packet]:
    """Shifts the timestamp of every packet by a fixed offset.

    Args:
        packets: List of scapy Packet objects to shift.
        offset: Seconds to add to each packet's timestamp.

    Returns:
        The same packet list with updated timestamps (mutated in place).
    """
    for pkt in packets:
        pkt.time = float(pkt.time) + offset
    return packets


def merge_captures(
    cap1_path: Path,
    cap2_path: Path,
    output_path: Path,
    gap_seconds: float = DEFAULT_GAP_SECONDS,
) -> None:
    """Merges two pcapng captures with continuous timestamps.

    The second capture is time-shifted so its first packet arrives
    ``gap_seconds`` after the last packet of the first capture.

    Args:
        cap1_path: Path to the first (earlier) capture file.
        cap2_path: Path to the second capture file.
        output_path: Path for the merged output file.
        gap_seconds: Time gap (in seconds) to insert between the two captures.

    Raises:
        FileNotFoundError: If either input file does not exist.
        ValueError: If either capture is empty.
    """
    pkts1 = read_packets(cap1_path)
    pkts2 = read_packets(cap2_path)

    if not pkts1:
        raise ValueError(f"Capture 1 is empty: {cap1_path}")
    if not pkts2:
        raise ValueError(f"Capture 2 is empty: {cap2_path}")

    t1_start = float(pkts1[0].time)
    t1_end   = float(pkts1[-1].time)
    t2_start = float(pkts2[0].time)

    logger.info("Capture 1 — start: %.6f  end: %.6f  duration: %.3f s",
                t1_start, t1_end, t1_end - t1_start)
    logger.info("Capture 2 — start: %.6f  end: %.6f  duration: %.3f s",
                t2_start, float(pkts2[-1].time), float(pkts2[-1].time) - t2_start)

    # Shift cap2 so that its first packet is t1_end + gap_seconds
    offset = (t1_end + gap_seconds) - t2_start
    logger.info("Applying offset to capture 2: %.6f s (gap = %.3f ms)",
                offset, gap_seconds * 1000)

    pkts2 = shift_timestamps(pkts2, offset)

    logger.info("Writing merged capture to: %s", output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_packets = pkts1 + pkts2
    with PcapNgWriter(str(output_path)) as writer:
        for pkt in all_packets:
            writer.write(pkt)

    logger.info("Done — %d total packets written", len(all_packets))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Merge two .pcapng captures with continuous timestamps."
    )
    parser.add_argument("cap1",  type=Path, help="First (earlier) capture file.")
    parser.add_argument("cap2",  type=Path, help="Second capture file.")
    parser.add_argument("output", type=Path, help="Output merged .pcapng file.")
    parser.add_argument(
        "--gap-ms",
        type=float,
        default=DEFAULT_GAP_SECONDS * 1000,
        metavar="MS",
        help="Gap in milliseconds between the two captures (default: 1 ms).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser


def main() -> None:
    """Entry point for the merge_pcap CLI."""
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    merge_captures(
        cap1_path=args.cap1,
        cap2_path=args.cap2,
        output_path=args.output,
        gap_seconds=args.gap_ms / 1000.0,
    )


if __name__ == "__main__":
    main()