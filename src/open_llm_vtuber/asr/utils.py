import os
import time
import requests
import tarfile
from pathlib import Path
from tqdm import tqdm
from loguru import logger


def get_github_asset_url(owner, repo, release_tag, filename_without_ext):
    """
    Fetch the URL of a GitHub release asset by its filename (without extension).

    Args:
        owner (str): The owner of the repository.
        repo (str): The name of the repository.
        release_tag (str): The tag of the release.
        filename_without_ext (str): The filename to search for (without extension).

    Returns:
        str: The download URL of the matched asset, or None if no match is found.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{release_tag}"
    headers = {}  # Add authentication headers if needed

    try:
        # Make a GET request to fetch release data
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # Parse the JSON response
        release_data = response.json()
        assets = release_data.get("assets", [])

        # Look for a matching file
        for asset in assets:
            if asset["name"].startswith(filename_without_ext):
                logger.info(f"Match found: {asset['name']}")
                return asset["browser_download_url"]

        # If no match found, log the error
        logger.error(
            f"No match found for filename: {filename_without_ext} in release {release_tag}."
        )
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"An error occurred while fetching release data: {e}")
        return None


def download_and_extract(url: str, output_dir: str) -> Path:
    """
    Download a file from a URL and extract it if it is a tar.bz2 archive.

    Args:
        url (str): The URL to download the file from.
        output_dir (str): The directory to save the downloaded file.

    Returns:
        Path: Path to the extracted directory if it's a tar.bz2 file,
             otherwise Path to the downloaded file.
    """
    # Create the output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Get the file name from the URL
    file_name = url.split("/")[-1]
    file_path = os.path.join(output_dir, file_name)

    # Extract the root directory name from the filename (removing .tar.bz2)
    root_dir = file_name.replace(".tar.bz2", "")
    extracted_dir_path = Path(output_dir) / root_dir

    # Check if the extracted directory already exists
    if extracted_dir_path.exists():
        logger.info(
            f"✅ The directory {extracted_dir_path} already exists. I would assume that the model is already downloaded and we are ready to go. Skipping download and extraction."
        )
        return extracted_dir_path

    # Download the file. The speech model is ~1GB and the first launch fetches it
    # over the open internet, so on flaky home wifi a single attempt often stalls or
    # drops. Use a connect/read timeout (a stalled stream raises instead of hanging
    # forever) and retry a few times with backoff, cleaning up any partial file
    # between attempts. (A total failure here is non-fatal — the app still opens and
    # just disables voice input — but a retry avoids that for a transient blip.)
    logger.info(f"🏃‍♂️Downloading {url} to {file_path}...")
    attempts = 3
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            # (connect timeout, per-read timeout) — the overall download may still
            # take many minutes; only a stalled socket trips the 60s read timeout.
            response = requests.get(url, stream=True, timeout=(15, 60))
            response.raise_for_status()  # Raise an error for bad status codes
            total_size = int(response.headers.get("content-length", 0))
            logger.debug(f"Total file size: {total_size / 1024 / 1024:.2f} MB")

            with (
                open(file_path, "wb") as f,
                tqdm(
                    desc=file_name,
                    total=total_size,
                    unit="iB",
                    unit_scale=True,
                    unit_divisor=1024,
                ) as pbar,
            ):
                for chunk in response.iter_content(chunk_size=8192):
                    size = f.write(chunk)
                    pbar.update(size)
            last_err = None
            break
        except Exception as e:
            last_err = e
            logger.warning(
                f"Download attempt {attempt}/{attempts} for {file_name} failed "
                f"({type(e).__name__}: {e})."
            )
            # Drop the partial file so the retry starts clean.
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                pass
            if attempt < attempts:
                time.sleep(2 * attempt)  # simple linear backoff
    if last_err is not None:
        raise last_err

    logger.info(f"Downloaded {file_name} successfully.")

    # Extract the tar.bz2 file
    if file_name.endswith(".tar.bz2"):
        logger.info(f"Extracting {file_name}...")
        with tarfile.open(file_path, "r:bz2") as tar:
            tar.extractall(path=output_dir)
        logger.info("Extraction completed.")

        # Delete the compressed file
        os.remove(file_path)
        logger.debug(f"Deleted the compressed file: {file_name}")

        return extracted_dir_path
    else:
        logger.warning("The downloaded file is not a tar.bz2 archive.")
        return Path(file_path)


def check_and_extract_local_file(url: str, output_dir: str) -> Path | None:
    """
    Check if a local file exists and extract it if it is a tar.bz2 archive.

    Args:
        url (str): The URL of the file.
        output_dir (str): The directory to save the extracted files.

    Returns:
        Path | None: Path to the extracted directory if it's a tar.bz2 file,
            otherwise None.
    """
    # Get the file name from the URL
    file_name = url.split("/")[-1]
    compressed_path = Path(output_dir) / file_name

    # Check if the compressed file exists and is a tar.bz2 archive
    extracted_dir = Path(output_dir) / file_name.replace(".tar.bz2", "")

    if extracted_dir.exists():
        logger.info(
            f"✅ Extracted directory exists: {extracted_dir}, no operation needed."
        )
        return extracted_dir

    if compressed_path.exists() and file_name.endswith(".tar.bz2"):
        logger.info(f"🔍 Found local archive file: {compressed_path}")

        try:
            logger.info("⏳ Extracting archive file...")
            with tarfile.open(compressed_path, "r:bz2") as tar:
                tar.extractall(path=output_dir)
            logger.success(f"Extracted archive to the path: {extracted_dir}")
            os.remove(compressed_path)  # Remove the compressed file
            return extracted_dir
        except Exception as e:
            logger.error(f"Fail to extract file: {str(e)}")
            return None

    logger.warning(f"Local file not found or not a tar.bz2 archive: {compressed_path}")
    return None


if __name__ == "__main__":
    url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
    output_dir = "./models"

    # Try local extraction first.
    local_result = check_and_extract_local_file(url, output_dir)

    # Download if not available locally.
    if local_result is None:
        logger.info("Local archive not found. Starting download...")
        download_and_extract(url, output_dir)
    else:
        logger.info("Extraction completed using local file.")
