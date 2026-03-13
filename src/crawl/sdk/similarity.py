"""Near-duplicate similarity helpers for crawled page content."""

import hashlib
import re

DEFAULT_SIMHASH_BIT_WIDTH = 64
DEFAULT_SIMHASH_THRESHOLD = 3
DEFAULT_TOKEN_WIDTH = 4
DEFAULT_MAX_TEXT_LENGTH = 50000
DEFAULT_MAX_TOKENS = 5000


def normalize_similarity_text(
    text: str,
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
) -> str:
    """Normalize text before similarity fingerprinting.

    Args:
        text: Source text to normalize.
        max_length: Maximum normalized text length to keep.

    Returns:
        Lowercased whitespace-normalized text.
    """
    normalized = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if max_length <= 0:
        return normalized
    return normalized[:max_length]


def generate_text_ngrams(text: str, token_width: int = DEFAULT_TOKEN_WIDTH) -> list[str]:
    """Generate fixed-width character n-grams from normalized text.

    Args:
        text: Normalized text.
        token_width: Character width for each shingle.

    Returns:
        Ordered list of text shingles.
    """
    cleaned_text = normalize_similarity_text(text, max_length=0)
    token_width = max(1, token_width)
    if not cleaned_text:
        return []
    if len(cleaned_text) <= token_width:
        return [cleaned_text]
    return [cleaned_text[index : index + token_width] for index in range(len(cleaned_text) - token_width + 1)]


def hash_similarity_token(
    token: str,
    bit_width: int = DEFAULT_SIMHASH_BIT_WIDTH,
) -> int:
    """Hash a similarity token into a fixed-width integer fingerprint.

    Args:
        token: Token or shingle to hash.
        bit_width: Bit width of the target fingerprint.

    Returns:
        Integer token fingerprint.
    """
    digest_size = max(1, bit_width // 8)
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=digest_size).digest()
    return int.from_bytes(digest, "big")


def compute_simhash(
    text: str,
    bit_width: int = DEFAULT_SIMHASH_BIT_WIDTH,
    token_width: int = DEFAULT_TOKEN_WIDTH,
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> int | None:
    """Compute a simhash-style fingerprint for page text.

    Args:
        text: Source text to fingerprint.
        bit_width: Bit width of the target fingerprint.
        token_width: Character width for shingles.
        max_length: Maximum normalized text length to fingerprint.
        max_tokens: Maximum number of shingles to include.

    Returns:
        Integer fingerprint or ``None`` when no text is available.
    """
    normalized_text = normalize_similarity_text(text, max_length=max_length)
    if not normalized_text:
        return None

    token_width = max(1, token_width)
    max_tokens = max(1, max_tokens)
    weights = [0] * bit_width

    if len(normalized_text) <= token_width:
        tokens = [normalized_text]
    else:
        token_count = min(len(normalized_text) - token_width + 1, max_tokens)
        tokens = [normalized_text[index : index + token_width] for index in range(token_count)]

    for token in tokens:
        token_hash = hash_similarity_token(token, bit_width=bit_width)
        for bit_index in range(bit_width):
            if token_hash & (1 << bit_index):
                weights[bit_index] += 1
            else:
                weights[bit_index] -= 1

    fingerprint = 0
    for bit_index, score in enumerate(weights):
        if score >= 0:
            fingerprint |= 1 << bit_index
    return fingerprint


def format_simhash(
    value: int,
    bit_width: int = DEFAULT_SIMHASH_BIT_WIDTH,
) -> str:
    """Format a simhash integer as a zero-padded hexadecimal string.

    Args:
        value: Integer fingerprint.
        bit_width: Bit width of the fingerprint.

    Returns:
        Hexadecimal fingerprint string.
    """
    hex_width = max(1, bit_width // 4)
    return f"{value:0{hex_width}x}"


def parse_simhash(value: str | int | None) -> int | None:
    """Parse a simhash value from hex-string or integer form.

    Args:
        value: Value to parse.

    Returns:
        Integer fingerprint or ``None`` when parsing fails.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 16)
    except ValueError:
        return None


def simhash_distance(left: int, right: int) -> int:
    """Compute the Hamming distance between two simhash integers.

    Args:
        left: Left fingerprint.
        right: Right fingerprint.

    Returns:
        Bit-distance between the two fingerprints.
    """
    return (left ^ right).bit_count()


def build_simhash_bucket_keys(
    value: int,
    max_distance: int = DEFAULT_SIMHASH_THRESHOLD,
    bit_width: int = DEFAULT_SIMHASH_BIT_WIDTH,
) -> list[tuple[int, int]]:
    """Build bucket keys for simhash candidate lookup.

    Args:
        value: Fingerprint value.
        max_distance: Maximum tolerated Hamming distance.
        bit_width: Fingerprint bit width.

    Returns:
        Bucket keys used for approximate candidate lookup.
    """
    partition_count = max(1, max_distance + 1)
    base_size, remainder = divmod(bit_width, partition_count)
    offset = 0
    keys = []

    for partition_index in range(partition_count):
        partition_size = base_size + (1 if partition_index < remainder else 0)
        mask = (1 << partition_size) - 1
        partition_value = (value >> offset) & mask
        keys.append((partition_index, partition_value))
        offset += partition_size

    return keys


def add_simhash_to_index(
    item_id: str,
    value: int,
    bucket_index: dict[tuple[int, int], set[str]],
    max_distance: int = DEFAULT_SIMHASH_THRESHOLD,
    bit_width: int = DEFAULT_SIMHASH_BIT_WIDTH,
) -> None:
    """Add a fingerprint to a bucketed simhash index.

    Args:
        item_id: Stable identifier for the fingerprint owner.
        value: Fingerprint value.
        bucket_index: Mutable bucket index.
        max_distance: Maximum tolerated Hamming distance.
        bit_width: Fingerprint bit width.
    """
    for bucket_key in build_simhash_bucket_keys(value, max_distance=max_distance, bit_width=bit_width):
        bucket_index.setdefault(bucket_key, set()).add(item_id)


def find_simhash_match(
    value: int,
    fingerprints: dict[str, int],
    bucket_index: dict[tuple[int, int], set[str]],
    max_distance: int = DEFAULT_SIMHASH_THRESHOLD,
    bit_width: int = DEFAULT_SIMHASH_BIT_WIDTH,
) -> tuple[str, int] | None:
    """Find the nearest indexed fingerprint within the configured threshold.

    Args:
        value: Candidate fingerprint value.
        fingerprints: Indexed fingerprint values by identifier.
        bucket_index: Bucketed candidate index.
        max_distance: Maximum tolerated Hamming distance.
        bit_width: Fingerprint bit width.

    Returns:
        Matching identifier and distance, or ``None``.
    """
    candidate_ids = set()
    for bucket_key in build_simhash_bucket_keys(value, max_distance=max_distance, bit_width=bit_width):
        candidate_ids.update(bucket_index.get(bucket_key, set()))

    best_match = None
    for candidate_id in candidate_ids:
        candidate_value = fingerprints.get(candidate_id)
        if candidate_value is None:
            continue
        distance = simhash_distance(value, candidate_value)
        if distance > max_distance:
            continue
        if best_match is None or distance < best_match[1]:
            best_match = (candidate_id, distance)

    return best_match
