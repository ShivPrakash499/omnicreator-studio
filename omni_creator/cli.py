"""
OMNI CREATOR — Command-Line Studio Interface (`omni_creator/cli.py`)
====================================================================
Usage Examples:
1. Dry-Run Mode (Generates SEO Keyword Strategy, 5-Beat Hinglish Script Blueprint,
   3 A/B 4K Thumbnails, 3D Start/End Keyframes, and Credit Estimate WITHOUT spending video credits):
   ```powershell
   python omni_cli.py --class-level "Class 10" --subject "Physics" --chapter "Light — Reflection and Refraction" --section "Refraction of Light, Glass Slab Lateral Shift & Snell's Law in 3D" --format "16:9_LongForm" --dry-run
   ```

2. Full 4K 3D Production Render (`final_video_4k.mp4` + Thumbnails + YouTube SEO Publish Sheet):
   ```powershell
   python omni_cli.py --class-level "Class 12" --subject "Physics" --chapter "Current Electricity" --section "Drift Velocity Derivation (I = nAe v_d), Mobility & Ohm's Law Limitations" --format "16:9_LongForm"
   ```
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import List, Optional

from config.models import OmniModelConfig
from omni_creator.compositor_and_packager import OmniProductionOutput, run_compositor_and_packager
from omni_creator.script_and_pedagogy_agent import generate_chapter_video_blueprint
from omni_creator.seo_keyword_engine import run_seo_keyword_engine
from schemas.blueprint import OmniCreatorInput


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni_cli",
        description="OMNI CREATOR — Ultra-Realistic 4K 3D Hinglish Science Video & SEO Engine (Classes 9-12)",
    )
    parser.add_argument(
        "--class-level",
        default="Class 10",
        choices=["Class 9", "Class 10", "Class 11", "Class 12"],
        help="Target NCERT/CBSE Class Level (default: 'Class 10').",
    )
    parser.add_argument(
        "--subject",
        default="Physics",
        choices=["Physics", "Chemistry", "Biology"],
        help="Target Science Subject (default: 'Physics').",
    )
    parser.add_argument(
        "--chapter",
        default="Light — Reflection and Refraction",
        help="NCERT 2026-27 Rationalized Chapter Name.",
    )
    parser.add_argument(
        "--section",
        default="Full Chapter Modular",
        help="Specific chapter sub-section or 'Full Chapter Modular'.",
    )
    parser.add_argument(
        "--format",
        default="16:9_LongForm",
        choices=["16:9_LongForm", "9:16_Shorts"],
        help="Output video format: '16:9_LongForm' or '9:16_Shorts'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate SEO Keywords, 5-Beat Hinglish Script, 3 A/B 4K Thumbnails, and 3D Keyframes without spending video generation credits.",
    )
    return parser


def run_omni_pipeline(
    spec: OmniCreatorInput,
    *,
    dry_run: bool = False,
    config: Optional[OmniModelConfig] = None,
) -> OmniProductionOutput:
    """Executes the complete 5-module Omni Creator pipeline and returns `OmniProductionOutput`."""
    cfg = config or OmniModelConfig()
    kw_strategy = run_seo_keyword_engine(spec, config=cfg)
    blueprint = generate_chapter_video_blueprint(spec, keyword_strategy=kw_strategy, config=cfg)
    return run_compositor_and_packager(blueprint, config=cfg, dry_run=dry_run)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    spec = OmniCreatorInput(
        class_level=args.class_level,  # type: ignore[arg-type]
        subject=args.subject,          # type: ignore[arg-type]
        chapter_name=args.chapter,
        chapter_section=args.section,
        video_format=args.format,      # type: ignore[arg-type]
    )

    print("=" * 84)
    print("🌌 OMNI CREATOR — ULTRA-REALISTIC 4K 3D HINGLISH SCIENCE VIDEO & SEO ENGINE")
    print("=" * 84)
    print(f"• Class & Subject : {spec.class_level} • {spec.subject}")
    print(f"• Chapter         : {spec.chapter_name}")
    print(f"• Section         : {spec.chapter_section}")
    print(f"• Video Format    : {spec.video_format} ({spec.aspect_ratio})")
    print(f"• Execution Mode  : {'DRY-RUN (No Video Credits Spent)' if args.dry_run else 'FULL 4K 3D PRODUCTION'}")
    print("-" * 84)

    result = run_omni_pipeline(spec, dry_run=args.dry_run)

    print("\n✅ PIPELINE COMPLETED SUCCESSFULLY!")
    print(f"📁 Output Bundle Directory : {result.bundle_dir.resolve()}")
    print(f"📊 SEO Metadata JSON       : {result.seo_json_path.resolve()}")
    print(f"📝 YouTube Publish Sheet   : {result.publish_sheet_md_path.resolve()}")
    for k, p in result.thumbnail_paths.items():
        print(f"🖼️  4K Thumbnail ({k}) : {p.resolve()}")
    if result.final_video_path:
        print(f"🎬 Final 4K 3D Video MP4   : {result.final_video_path.resolve()}")
    print("\n💰 Credit & Cost Summary:")
    print(json.dumps(result.credit_estimate, indent=2))
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
