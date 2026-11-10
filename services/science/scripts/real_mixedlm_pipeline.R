# Independent end-to-end reference for METH-REAL-TREND (RES-619).
# Input: a verbatim CSV dump of the Mendeley DATA.xlsx "DATA" sheet (no
# DynamisScience transformation). Derives the analysis rows itself, fits
# lmer ML, and writes fixed effects, BLUPs, conditional/marginal fitted values,
# conditional Pearson residuals, Blom positions and convergence details.
# Usage: Rscript real_mixedlm_pipeline.R <DATA.csv> <output dir>
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: Rscript real_mixedlm_pipeline.R <DATA.csv> <output dir>")
out <- args[[2]]
dir.create(out, showWarnings = FALSE, recursive = TRUE)
suppressPackageStartupMessages(library(lme4))

raw <- read.csv(args[[1]], stringsAsFactors = FALSE)
d <- raw[tolower(raw$prevspost) == "post" & !is.na(suppressWarnings(as.numeric(raw$CMJht))), ]
d <- data.frame(
  subject_id = sprintf("MEN-%02d", as.integer(d$ID)),
  occasion = as.integer(d$COND),
  cmj_height_cm = as.numeric(d$CMJht) * 100
)
d <- d[order(d$subject_id, d$occasion), ]
d$occasion_c <- d$occasion - 1
write.csv(d, file.path(out, "derived_rows.csv"), row.names = FALSE)

fit <- lmer(cmj_height_cm ~ occasion_c + (1 + occasion_c | subject_id), data = d, REML = FALSE,
            control = lmerControl(optimizer = "bobyqa"))
nm <- update(fit, control = lmerControl(optimizer = "Nelder_Mead"))
X <- model.matrix(fit)
marginal_fit <- as.vector(X %*% fixef(fit))
conditional_fit <- fitted(fit)
sigma_hat <- sigma(fit)
# lme4 type = "pearson" is NOT divided by sigma for Gaussian lmerMod (lme4 2.1.0); scale explicitly.
pearson <- residuals(fit) / sigma_hat
ord <- order(pearson)
n <- length(pearson)
blom <- (seq_len(n) - 3 / 8) / (n + 1 / 4)
write.csv(data.frame(
  subject_id = d$subject_id, occasion = d$occasion,
  marginal_fitted = marginal_fit, conditional_fitted = as.vector(conditional_fit),
  marginal_residual = d$cmj_height_cm - marginal_fit, conditional_residual = as.vector(residuals(fit)),
  conditional_pearson = as.vector(pearson)
), file.path(out, "fitted_residuals.csv"), row.names = FALSE)
write.csv(data.frame(rank = seq_len(n), blom_p = blom, theoretical = qnorm(blom), observed = as.vector(pearson[ord])),
          file.path(out, "qq.csv"), row.names = FALSE)
re <- ranef(fit)$subject_id
write.csv(data.frame(subject_id = rownames(re), intercept = re[, 1], slope = re[, 2]), file.path(out, "blups.csv"), row.names = FALSE)
vc <- as.data.frame(VarCorr(fit))
ci_wald <- confint(fit, method = "Wald", parm = "beta_")
ci_profile <- tryCatch(confint(fit, method = "profile", parm = "beta_", signames = FALSE), error = function(e) matrix(NA, 2, 2))
summary_row <- data.frame(
  nobs = nobs(fit), ngrps = ngrps(fit), logLik = as.numeric(logLik(fit)), logLik_nelder_mead = as.numeric(logLik(nm)),
  intercept = fixef(fit)[[1]], slope = fixef(fit)[[2]],
  se_intercept = sqrt(vcov(fit)[1, 1]), se_slope = sqrt(vcov(fit)[2, 2]),
  slope_wald_low = ci_wald[2, 1], slope_wald_high = ci_wald[2, 2],
  slope_profile_low = ci_profile[2, 1], slope_profile_high = ci_profile[2, 2],
  slope_t_df20_low = fixef(fit)[[2]] - qt(0.975, ngrps(fit) - 1) * sqrt(vcov(fit)[2, 2]),
  slope_t_df20_high = fixef(fit)[[2]] + qt(0.975, ngrps(fit) - 1) * sqrt(vcov(fit)[2, 2]),
  var_intercept = vc$vcov[1], var_slope = vc$vcov[2], cov_intercept_slope = vc$vcov[3], sigma = sigma_hat,
  cor_intercept_slope = vc$sdcor[3], singular = isSingular(fit),
  converged = length(fit@optinfo$conv$lme4$messages) == 0,
  pearson_sd = sd(pearson), shapiro_p_pearson = shapiro.test(as.vector(pearson))$p.value,
  shapiro_p_blup_intercept = shapiro.test(re[, 1])$p.value, shapiro_p_blup_slope = shapiro.test(re[, 2])$p.value
)
write.csv(summary_row, file.path(out, "summary.csv"), row.names = FALSE)
print(t(summary_row))
