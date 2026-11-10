# Independent end-to-end reference for METH-REAL-RELIABILITY (RES-619).
# Starts from the raw MoveSmart archive, not from DynamisScience tables:
# file discovery, force/IMU matching, plate summation, acquisition ordering,
# first-k selection, two-way ANOVA, ICC(1,1)/(2,1)/(3,1), CIs, TE and MDC95.
# Usage: Rscript real_reliability_pipeline.R <Dataset dir> <output dir> [activity=walk] [max_trials=8]
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: Rscript real_reliability_pipeline.R <Dataset dir> <output dir> [prefix] [max_trials]")
root <- args[[1]]
out <- args[[2]]
prefix <- if (length(args) >= 3) args[[3]] else "walk"
max_trials <- if (length(args) >= 4) as.integer(args[[4]]) else 8L
imu_activity <- c(walk = "Walking", jog = "Jogging", run = "Running", heel = "Heel", drop = "Drop")[[prefix]]
dir.create(out, showWarnings = FALSE, recursive = TRUE)

read_plate <- function(path) {
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  header <- grep("^SAMPLE,", lines)[1]
  stamp <- sub('^﻿?TIME_STAMP,"([^"]+)".*$', "\\1", grep("TIME_STAMP,", lines, value = TRUE)[1])
  data <- read.csv(text = lines[header:length(lines)], stringsAsFactors = FALSE)
  fz <- suppressWarnings(as.numeric(data$Force_Z))
  list(fz = fz, stamp = as.POSIXct(stamp, format = "%Y-%m-%d, %H:%M:%OS", tz = "UTC"))
}

rows <- list()
for (participant in sort(list.dirs(root, full.names = FALSE, recursive = FALSE))) {
  folder <- file.path(root, participant)
  files <- list.files(folder, pattern = paste0("^", prefix, "[0-9]+_f_[678]\\.csv$"))
  imu <- list.files(folder, pattern = paste0("^", imu_activity, "_(Waist|Wrist)_Trial_.*_ID_[0-9]+_"))
  imu_trials <- unique(as.integer(sub(".*_ID_([0-9]+)_.*", "\\1", imu)))
  trials <- sort(unique(as.integer(sub(paste0("^", prefix, "([0-9]+)_f_.*$"), "\\1", files))))
  for (trial in trials) {
    plates <- files[as.integer(sub(paste0("^", prefix, "([0-9]+)_f_.*$"), "\\1", files)) == trial]
    signals <- lapply(file.path(folder, plates), read_plate)
    n <- min(sapply(signals, function(item) length(item$fz)))
    total <- Reduce(`+`, lapply(signals, function(item) { v <- item$fz[seq_len(n)]; v[is.na(v)] <- 0; v }))
    rows[[length(rows) + 1]] <- data.frame(
      participant = participant,
      subject_id = paste0("MS-", sprintf("%02d", as.integer(sub("^P([0-9]+)-.*$", "\\1", participant)))),
      trial = trial,
      acquired_utc = format(min(do.call(c, lapply(signals, `[[`, "stamp"))), "%Y-%m-%d %H:%M:%OS3"),
      plates = length(plates),
      imu_matched = trial %in% imu_trials,
      peak_fz_n = max(total)
    )
  }
}
trials <- do.call(rbind, rows)
trials <- trials[order(trials$subject_id, trials$acquired_utc), ]
trials$acquisition_rank <- ave(seq_len(nrow(trials)), trials$subject_id, FUN = seq_along)
trials$order_matches_trial_number <- ave(trials$trial, trials$subject_id, FUN = function(x) x == sort(x))
write.csv(trials, file.path(out, "raw_trials.csv"), row.names = FALSE)

eligible <- trials[trials$imu_matched, ]
counts <- table(eligible$subject_id)
keep <- names(counts)[counts >= 2]
k <- min(max_trials, min(counts[keep]))
selected <- do.call(rbind, lapply(keep, function(s) head(eligible[eligible$subject_id == s, ], k)))
selected$position <- ave(seq_len(nrow(selected)), selected$subject_id, FUN = seq_along)
write.csv(selected, file.path(out, "selected_trials.csv"), row.names = FALSE)

d <- data.frame(subject = factor(selected$subject_id), trial = factor(selected$position), y = selected$peak_fz_n)
n <- nlevels(d$subject)
tab <- summary(aov(y ~ subject + trial, data = d))[[1]]
ms <- setNames(tab[["Mean Sq"]], trimws(rownames(tab)))
df <- setNames(tab[["Df"]], trimws(rownames(tab)))
msr <- ms[["subject"]]; msc <- ms[["trial"]]; mse <- ms[["Residuals"]]
msw <- sum(tapply(d$y, d$subject, function(v) sum((v - mean(v))^2))) / (n * (k - 1))
alpha <- 0.05
f3 <- msr / mse
fl3 <- f3 / qf(1 - alpha / 2, n - 1, (n - 1) * (k - 1))
fu3 <- f3 * qf(1 - alpha / 2, (n - 1) * (k - 1), n - 1)
f1 <- msr / msw
fl1 <- f1 / qf(1 - alpha / 2, n - 1, n * (k - 1))
fu1 <- f1 * qf(1 - alpha / 2, n * (k - 1), n - 1)
te <- sqrt(mse)
result <- data.frame(
  n_subjects = n, k_trials = k, trials_available = nrow(eligible), trials_used = nrow(selected),
  df_subject = df[["subject"]], df_trial = df[["trial"]], df_error = df[["Residuals"]],
  ms_subject = msr, ms_trial = msc, ms_error = mse, ms_within = msw,
  p_trial_effect = tab[["Pr(>F)"]][2],
  icc_3_1 = (msr - mse) / (msr + (k - 1) * mse),
  icc_3_1_ci_low = (fl3 - 1) / (fl3 + k - 1), icc_3_1_ci_high = (fu3 - 1) / (fu3 + k - 1),
  icc_1_1 = (msr - msw) / (msr + (k - 1) * msw),
  icc_1_1_ci_low = (fl1 - 1) / (fl1 + k - 1), icc_1_1_ci_high = (fu1 - 1) / (fu1 + k - 1),
  icc_2_1 = (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n),
  typical_error_n = te, mdc95_n = qnorm(0.975) * sqrt(2) * te,
  all_orders_match_trial_number = all(trials$order_matches_trial_number)
)
write.csv(result, file.path(out, "icc.csv"), row.names = FALSE)
print(t(result))
