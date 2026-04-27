# AUP Learning Cloud Base Images

## GPU Base Image (`Dockerfile.rocm`)

Multi-target ROCm GPU base image. Set `GPU_TARGET` to build for any supported architecture.

### Supported Targets

| GPU_TARGET    | Arch     | GPUs                            | Pip wheel path (derived) |
|---------------|----------|---------------------------------|--------------------------|
| gfx110x       | RDNA 3   | gfx1100/1101/1102/1103 (dGPU)   | gfx110X-all              |
| gfx1150       | RDNA 3.5 | Strix (Radeon 890M)             | gfx1150                  |
| gfx1151       | RDNA 3.5 | Strix Halo (Radeon 8060S)       | gfx1151                  |
| gfx1152       | RDNA 3.5 |                                 | gfx1152                  |
| gfx120x       | RDNA 4   | gfx1201 (dGPU: RX 9070 XT, R9700, RX 9600 GRE, …) | gfx120X-all |

The `GPU_TARGET` value is the short name used by the AMD apt repo
(`amdrocm7.11-<GPU_TARGET>`) and as the image-tag suffix. The pip wheel index
at <https://repo.amd.com/rocm/whl/> uses the "long" `gfxNNNX-all` path for
the generic RDNA 3 / RDNA 4 buckets; `Dockerfile.rocm` maps short → long
automatically. CI passes `PYTORCH_WHL_TARGET` explicitly (see
`.github/build-config.json`).

### Build

```bash
# Default target (gfx1151 = Strix Halo)
docker build -t ghcr.io/amdresearch/auplc-base:latest --file Dockerfile.rocm .

# Specific target
docker build --build-arg GPU_TARGET=gfx120x \
  -t ghcr.io/amdresearch/auplc-base:latest-gfx120x --file Dockerfile.rocm .

# Using make (from dockerfiles/ directory)
make base-rocm                         # default target
make base-rocm GPU_TARGET=gfx120x      # RDNA 4 desktop GPUs
make base-rocm GPU_TARGET=gfx110x      # RDNA 3 desktop GPUs
```

### Override URLs

For edge cases, override the derived URLs directly:

```bash
docker build \
  --build-arg ROCM_TARBALL_URL=https://custom.url/rocm.tar.gz \
  --build-arg PYTORCH_INDEX_URL=https://custom.url/whl/ \
  --file Dockerfile.rocm .
```

## CPU Base Image (`Dockerfile.cpu`)

```bash
docker build -t ghcr.io/amdresearch/auplc-default:latest --file Dockerfile.cpu .
```
