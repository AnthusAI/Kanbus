const { execSync } = require("node:child_process");
const { existsSync, statSync } = require("node:fs");

const AUDIO_VALIDATION_PREFIX = "AUDIO_VALIDATION_FAILED";
const AUDIO_MIN_DURATION_SEC = 0.2;
const AUDIO_MIN_ACTIVITY_RATIO = 0.001;
const AUDIO_MIN_BYTES_WAV = 256;
const AUDIO_MIN_BYTES_MP4 = 1024;

const runCapture = (cmd, opts = {}) => {
  return execSync(cmd, { stdio: ["ignore", "pipe", "pipe"], ...opts });
};

const probeDurationSec = (assetPath) => {
  const output = runCapture(
    `ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "${assetPath}"`,
    { encoding: "utf8" },
  )
    .toString()
    .trim();
  const value = Number(output.split("\n")[0] || 0);
  return Number.isFinite(value) ? Math.max(0, value) : 0;
};

const probeAudioStreamCount = (assetPath) => {
  const output = runCapture(
    `ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "${assetPath}"`,
    { encoding: "utf8" },
  )
    .toString()
    .trim();
  if (!output) return 0;
  return output
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean).length;
};

const decodePcm = (assetPath, seconds = 6, sampleRateHz = 44100) => {
  return runCapture(
    `ffmpeg -v error -t ${seconds} -i "${assetPath}" -ac 1 -ar ${sampleRateHz} -f s16le pipe:1`,
    { encoding: "buffer", maxBuffer: 50 * 1024 * 1024 },
  );
};

const computeActivityRatio = (pcm, amplitudeThreshold = 200) => {
  if (!pcm || pcm.length < 2) {
    return { activityRatio: 0, isAllSilence: true };
  }
  const total = Math.floor(pcm.length / 2);
  let active = 0;
  for (let i = 0; i < total; i += 1) {
    const sample = pcm.readInt16LE(i * 2);
    if (sample >= amplitudeThreshold || sample <= -amplitudeThreshold) {
      active += 1;
    }
  }
  return {
    activityRatio: total ? active / total : 0,
    isAllSilence: active === 0,
  };
};

const validateAudioFile = (assetPath, options = {}) => {
  const {
    requireAudioStream = true,
    minBytes = AUDIO_MIN_BYTES_WAV,
    minDurationSec = AUDIO_MIN_DURATION_SEC,
    probeSeconds = 6,
    sampleRateHz = 44100,
    minActivityRatio = AUDIO_MIN_ACTIVITY_RATIO,
    checkSilence = true,
  } = options;

  const result = {
    path: assetPath,
    exists: false,
    bytes: 0,
    durationSec: 0,
    audioStreamCount: 0,
    activityRatio: 0,
    isAllSilence: null,
    valid: false,
    failures: [],
  };

  if (!existsSync(assetPath)) {
    result.failures.push("missing-file");
    return result;
  }
  result.exists = true;

  try {
    result.bytes = statSync(assetPath).size;
  } catch {
    result.failures.push("stat-failed");
  }
  if (result.bytes < minBytes) {
    result.failures.push(`bytes-below-min(${result.bytes}<${minBytes})`);
  }

  try {
    result.durationSec = probeDurationSec(assetPath);
  } catch {
    result.failures.push("probe-duration-failed");
  }
  if (result.durationSec < minDurationSec) {
    result.failures.push(`duration-below-min(${result.durationSec.toFixed(3)}<${minDurationSec})`);
  }

  try {
    result.audioStreamCount = probeAudioStreamCount(assetPath);
  } catch {
    result.failures.push("probe-streams-failed");
  }
  if (requireAudioStream && result.audioStreamCount < 1) {
    result.failures.push("missing-audio-stream");
  }

  const shouldInspectWaveform = checkSilence || minActivityRatio > 0;
  if (shouldInspectWaveform && (!requireAudioStream || result.audioStreamCount > 0)) {
    try {
      const secondsToProbe = Math.max(0.25, Math.min(probeSeconds, result.durationSec || probeSeconds));
      const pcm = decodePcm(assetPath, secondsToProbe, sampleRateHz);
      const { activityRatio, isAllSilence } = computeActivityRatio(pcm);
      result.activityRatio = activityRatio;
      result.isAllSilence = isAllSilence;
      if (checkSilence && isAllSilence) {
        result.failures.push("all-silence");
      }
      if (minActivityRatio > 0 && activityRatio < minActivityRatio) {
        result.failures.push(`activity-below-min(${activityRatio.toFixed(4)}<${minActivityRatio})`);
      }
    } catch {
      result.failures.push("waveform-check-failed");
    }
  }

  result.valid = result.failures.length === 0;
  return result;
};

const logValidationFailure = (label, validation) => {
  console.error(
    `${AUDIO_VALIDATION_PREFIX} label=${label} file=${validation.path} ` +
      `failures=${validation.failures.join("|")} bytes=${validation.bytes} ` +
      `duration_sec=${validation.durationSec.toFixed(3)} streams=${validation.audioStreamCount} ` +
      `activity_ratio=${(validation.activityRatio || 0).toFixed(4)}`,
  );
};

const assertAudioValidations = (stage, checks) => {
  const failures = [];
  for (const check of checks) {
    if (!check.validation.valid) {
      failures.push(check);
      logValidationFailure(check.label, check.validation);
    }
  }
  if (failures.length > 0) {
    console.error(`${AUDIO_VALIDATION_PREFIX} stage=${stage} total_failures=${failures.length} status=abort`);
    throw new Error(`Audio validation failed during ${stage}`);
  }
};

module.exports = {
  AUDIO_VALIDATION_PREFIX,
  AUDIO_MIN_DURATION_SEC,
  AUDIO_MIN_ACTIVITY_RATIO,
  AUDIO_MIN_BYTES_WAV,
  AUDIO_MIN_BYTES_MP4,
  validateAudioFile,
  assertAudioValidations,
};
