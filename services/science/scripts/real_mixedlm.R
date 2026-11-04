# Independent lme4 reference for the real-data CMJ longitudinal model.
# Usage: Rscript real_mixedlm.R <input.csv> <output_dir>
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: Rscript real_mixedlm.R <input.csv> <output_dir>")
input <- args[[1]]
output <- args[[2]]
dir.create(output, showWarnings = FALSE, recursive = TRUE)

suppressPackageStartupMessages(library(lme4))
d <- read.csv(input, stringsAsFactors = FALSE)
d$occasion_c <- d$occasion - 1
d$subject_id <- factor(d$subject_id)

fit <- lmer(
  cmj_height_cm ~ occasion_c + (1 + occasion_c | subject_id),
  data = d,
  REML = FALSE
)
fe <- fixef(fit)
se <- sqrt(diag(vcov(fit)))
write.csv(
  data.frame(term = names(fe), estimate = as.numeric(fe), se = as.numeric(se)),
  file.path(output, "fixed.csv"),
  row.names = FALSE
)
vc <- as.data.frame(VarCorr(fit))
write.csv(vc, file.path(output, "varcorr.csv"), row.names = FALSE)
write.csv(
  data.frame(
    logLik = as.numeric(logLik(fit)),
    nobs = nobs(fit),
    ngrps = length(unique(d$subject_id)),
    sigma = sigma(fit),
    singular = isSingular(fit),
    converged = length(fit@optinfo$conv$lme4$messages) == 0
  ),
  file.path(output, "fit.csv"),
  row.names = FALSE
)
cat("R lme4 reference complete\n")
