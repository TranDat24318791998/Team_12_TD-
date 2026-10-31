"""Optional image-to-video subprocess. Only loads a pre-downloaded local model."""
import argparse
from pathlib import Path


def generate(args):
    import torch
    from diffusers import LTXImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image

    model = Path(args.model).resolve()
    if not (model / 'model_index.json').is_file():
        raise RuntimeError('Cần thư mục model Diffusers local có model_index.json')
    dtype = torch.float32 if args.device == 'cpu' else torch.bfloat16
    pipe = LTXImageToVideoPipeline.from_pretrained(str(model), torch_dtype=dtype, local_files_only=True)
    if args.device == 'cuda':
        pipe.enable_model_cpu_offload()
    else:
        pipe.to(args.device)
    pipe.vae.enable_tiling()
    frames = pipe(image=load_image(args.image), prompt=args.prompt,
                  negative_prompt='warped product, extra blades, deformed hands, text, watermark',
                  height=512, width=512, num_frames=49, frame_rate=24, num_inference_steps=30,
                  generator=torch.Generator('cpu').manual_seed(args.seed)).frames[0]
    export_to_video(frames, args.output, fps=24)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('model', 'image', 'prompt', 'output', 'device'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--seed', type=int, default=42)
    generate(parser.parse_args())
