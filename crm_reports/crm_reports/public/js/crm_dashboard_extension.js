;(function () {
  "use strict"

  const TOOLBAR_ID =
    "crm-reports-advanced-toolbar"

  const DETAILS_ID =
    "crm-reports-dashboard-details"

  const MARKER_ID =
    "crm-reports-extension-marker"

  const REPORT_METHOD =
    "/api/method/crm_reports.api.dashboard_report.get_dashboard_report"

  let loading = false
  let reloadTimer = null

  function cleanValue(value) {
    if (
      value === null ||
      value === undefined
    ) {
      return ""
    }

    const cleaned = String(value).trim()

    if (
      !cleaned ||
      ["null", "none", "undefined"].includes(
        cleaned.toLowerCase(),
      )
    ) {
      return ""
    }

    return cleaned
  }

  function isDashboardRoute() {
    return (
      window.location.pathname
        .replace(/\/+$/, "") ===
      "/crm/dashboard"
    )
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;")
  }

  function formatNumber(value) {
    return new Intl.NumberFormat(
      "vi-VN",
      {
        maximumFractionDigits: 2,
      },
    ).format(Number(value || 0))
  }

  function formatCurrency(
    value,
    currency,
  ) {
    const code =
      cleanValue(currency) || "VND"

    return `${escapeHtml(code)} ${formatNumber(
      value,
    )}`
  }

  function formatPercent(value) {
    const number = Number(value || 0)

    if (number > 0) {
      return `↑ ${formatNumber(number)}%`
    }

    if (number < 0) {
      return `↓ ${formatNumber(
        Math.abs(number),
      )}%`
    }

    return "0%"
  }

  function defaultDates() {
    const toDate = new Date()
    const fromDate = new Date()

    fromDate.setDate(
      fromDate.getDate() - 29,
    )

    return {
      from_date:
        fromDate
          .toISOString()
          .slice(0, 10),

      to_date:
        toDate
          .toISOString()
          .slice(0, 10),
    }
  }

  function getStoredFilters() {
    return (
      window.CRMReportsFilters?.read?.()
      || {}
    )
  }

  function saveStoredFilters(filters) {
    window.CRMReportsFilters?.write?.(
      filters,
    )
  }

  function getLastDashboardParams() {
    return (
      window
        .__crmReportsLastDashboardParams
      || {}
    )
  }

  function getCurrentReportParams() {
    const fallbackDates =
      defaultDates()

    const dashboardParams =
      getLastDashboardParams()

    const customFilters =
      getStoredFilters()

    const params = {
      from_date:
        dashboardParams.from_date
        || fallbackDates.from_date,

      to_date:
        dashboardParams.to_date
        || fallbackDates.to_date,

      source:
        customFilters.source || null,

      territory:
        customFilters.territory || null,

      status:
        customFilters.status || null,

      team:
        customFilters.team || null,
    }

    const employee = cleanValue(
      dashboardParams.user,
    )

    if (employee) {
      params.employee = employee
    }

    return params
  }

  async function callReport(params) {
    const url = new URL(
      REPORT_METHOD,
      window.location.origin,
    )

    Object.entries(params || {}).forEach(
      ([key, value]) => {
        const cleaned =
          cleanValue(value)

        if (cleaned) {
          url.searchParams.set(
            key,
            cleaned,
          )
        }
      },
    )

    const response = await fetch(
      url.toString(),
      {
        method: "GET",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
        },
      },
    )

    const payload =
      await response.json()

    if (
      !response.ok ||
      payload.exc ||
      payload.exception
    ) {
      throw new Error(
        payload.exception ||
        payload.exc ||
        `HTTP ${response.status}`,
      )
    }

    return payload.message || payload
  }

  function findFilterRow() {
    const direct =
      document.querySelector(
        "div.p-5.pb-2.flex.items-center.gap-4",
      )

    if (direct) {
      return direct
    }

    const buttons = [
      ...document.querySelectorAll(
        "button",
      ),
    ]

    const dateButton = buttons.find(
      (button) =>
        /last|this|custom|ngày|tháng|tuần/i
          .test(
            button.textContent || "",
          ),
    )

    return dateButton?.parentElement
      || null
  }

  function findScrollContainer() {
    const direct =
      document.querySelector(
        "div.w-full.overflow-y-scroll",
      )

    if (direct) {
      return direct
    }

    return findFilterRow()
      ?.closest(
        "div[class*='overflow-y']",
      )
      || null
  }

  function ensureToolbarRoot() {
    let root =
      document.getElementById(
        TOOLBAR_ID,
      )

    if (root) {
      return root
    }

    const filterRow =
      findFilterRow()

    if (!filterRow) {
      return null
    }

    root =
      document.createElement("div")

    root.id = TOOLBAR_ID

    filterRow.insertAdjacentElement(
      "afterend",
      root,
    )

    return root
  }

  function ensureDetailsRoot() {
    let root =
      document.getElementById(
        DETAILS_ID,
      )

    if (root) {
      return root
    }

    const scrollContainer =
      findScrollContainer()

    if (!scrollContainer) {
      return null
    }

    root =
      document.createElement("section")

    root.id = DETAILS_ID

    scrollContainer.appendChild(root)

    return root
  }

  function uniqueValues(
    rows,
    key,
    selectedValue = "",
  ) {
    const values = new Set()

    ;(rows || []).forEach((row) => {
      const value = cleanValue(
        row?.[key],
      )

      if (value) {
        values.add(value)
      }
    })

    const selected =
      cleanValue(selectedValue)

    if (selected) {
      values.add(selected)
    }

    return [...values].sort(
      (left, right) =>
        left.localeCompare(
          right,
          "vi",
        ),
    )
  }

  function optionHtml(
    value,
    selectedValue,
  ) {
    const selected =
      String(value) ===
      String(selectedValue || "")

    return `
      <option
        value="${escapeHtml(value)}"
        ${selected ? "selected" : ""}
      >
        ${escapeHtml(value)}
      </option>
    `
  }

  function renderToolbar(
    report,
    optionsReport,
  ) {
    const root =
      ensureToolbarRoot()

    if (!root) {
      return
    }

    const stored =
      getStoredFilters()

    const meta =
      report.meta || {}

    const isManager =
      Boolean(meta.is_manager)

    const modeLabel =
      report.view_mode === "manager"
        ? "Manager View"
        : "Employee View"

    const sources = uniqueValues(
      optionsReport.source_analysis,
      "source",
      stored.source,
    )

    const territories = uniqueValues(
      optionsReport.territory_analysis,
      "territory",
      stored.territory,
    )

    const statuses = uniqueValues(
      optionsReport.funnel,
      "stage",
      stored.status,
    )

    const teams = uniqueValues(
      optionsReport.employee_ranking,
      "team",
      stored.team,
    )

    root.innerHTML = `
      <div class="crm-reports-filter-card">
        <div class="crm-reports-filter-header">
          <div>
            <div class="crm-reports-filter-title">
              CRM Reports — Bộ lọc nâng cao
            </div>

            <div class="crm-reports-filter-subtitle">
              ${escapeHtml(modeLabel)}
              ${
                meta.effective_employee
                  ? ` · ${escapeHtml(
                      meta.effective_employee,
                    )}`
                  : ""
              }
            </div>
          </div>

          <div class="crm-reports-view-note">
            Dùng Sales User phía trên để chuyển
            Manager/Employee.
          </div>
        </div>

        <div class="crm-reports-filter-grid">
          ${
            isManager
              ? `
                <label class="crm-reports-field">
                  <span>Team</span>

                  <select data-report-filter="team">
                    <option value="">
                      Tất cả team
                    </option>

                    ${teams
                      .map((value) =>
                        optionHtml(
                          value,
                          stored.team,
                        ),
                      )
                      .join("")}
                  </select>
                </label>
              `
              : ""
          }

          <label class="crm-reports-field">
            <span>Lead Source</span>

            <select data-report-filter="source">
              <option value="">
                Tất cả nguồn
              </option>

              ${sources
                .map((value) =>
                  optionHtml(
                    value,
                    stored.source,
                  ),
                )
                .join("")}
            </select>
          </label>

          <label class="crm-reports-field">
            <span>Territory</span>

            <select data-report-filter="territory">
              <option value="">
                Tất cả khu vực
              </option>

              ${territories
                .map((value) =>
                  optionHtml(
                    value,
                    stored.territory,
                  ),
                )
                .join("")}
            </select>
          </label>

          <label class="crm-reports-field">
            <span>Deal Status</span>

            <select data-report-filter="status">
              <option value="">
                Tất cả trạng thái
              </option>

              ${statuses
                .map((value) =>
                  optionHtml(
                    value,
                    stored.status,
                  ),
                )
                .join("")}
            </select>
          </label>

          <button
            type="button"
            class="crm-reports-reset"
            data-reset-report-filters
          >
            Xóa bộ lọc nâng cao
          </button>
        </div>
      </div>
    `

    root
      .querySelectorAll(
        "[data-report-filter]",
      )
      .forEach((field) => {
        field.addEventListener(
          "change",
          handleFilterChange,
        )
      })

    root
      .querySelector(
        "[data-reset-report-filters]",
      )
      ?.addEventListener(
        "click",
        resetFilters,
      )
  }

  function handleFilterChange(event) {
    const fieldname =
      event.target.dataset
        .reportFilter

    const stored =
      getStoredFilters()

    stored[fieldname] =
      event.target.value

    saveStoredFilters(stored)

    refreshNativeDashboard()
  }

  function resetFilters() {
    saveStoredFilters({})

    refreshNativeDashboard()
  }

  function refreshNativeDashboard() {
    const buttons = [
      ...document.querySelectorAll(
        "button",
      ),
    ]

    const refreshButton =
      buttons.find((button) =>
        /refresh|làm mới/i.test(
          button.textContent || "",
        ),
      )

    if (refreshButton) {
      refreshButton.click()

      scheduleReload(500)

      return
    }

    window.location.reload()
  }

  function tableHtml(columns, rows) {
    if (!rows?.length) {
      return `
        <div class="crm-reports-empty">
          Không có dữ liệu trong kỳ đã chọn.
        </div>
      `
    }

    return `
      <div class="crm-reports-table-wrapper">
        <table class="crm-reports-table">
          <thead>
            <tr>
              ${columns
                .map(
                  (column) =>
                    `<th>${escapeHtml(
                      column.label,
                    )}</th>`,
                )
                .join("")}
            </tr>
          </thead>

          <tbody>
            ${rows
              .map(
                (row, index) => `
                  <tr>
                    ${columns
                      .map((column) => {
                        const content =
                          column.render
                            ? column.render(
                                row,
                                index,
                              )
                            : escapeHtml(
                                row[
                                  column.key
                                ],
                              )

                        return `<td>${content}</td>`
                      })
                      .join("")}
                  </tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `
  }

  function actionListHtml(
    rows,
    currency,
  ) {
    if (!rows?.length) {
      return `
        <div class="crm-reports-empty">
          Không có Deal cần xử lý.
        </div>
      `
    }

    return `
      <div class="crm-reports-action-list">
        ${rows
          .slice(0, 25)
          .map(
            (row) => `
              <a
                class="crm-reports-action-item"
                href="${escapeHtml(
                  row.route || "#",
                )}"
              >
                <div class="crm-reports-action-main">
                  <strong>
                    ${escapeHtml(
                      row.title
                      || row.name,
                    )}
                  </strong>

                  ${
                    row.subtitle
                      ? `
                        <div class="crm-reports-muted">
                          ${escapeHtml(
                            row.subtitle,
                          )}
                        </div>
                      `
                      : ""
                  }
                </div>

                <div class="crm-reports-action-meta">
                  <span>
                    ${escapeHtml(
                      row.badge || "",
                    )}
                  </span>

                  <strong>
                    ${formatCurrency(
                      row.deal_value,
                      currency,
                    )}
                  </strong>
                </div>
              </a>
            `,
          )
          .join("")}
      </div>
    `
  }

  function sectionHtml(
    title,
    content,
  ) {
    return `
      <section class="crm-reports-section">
        <h2>${escapeHtml(title)}</h2>
        ${content}
      </section>
    `
  }

  function warningsHtml(warnings) {
    if (!warnings?.length) {
      return ""
    }

    return `
      <div class="crm-reports-warning">
        <strong>Cảnh báo dữ liệu</strong>

        <ul>
          ${warnings
            .map(
              (warning) =>
                `<li>${escapeHtml(
                  warning,
                )}</li>`,
            )
            .join("")}
        </ul>
      </div>
    `
  }

  function managerDetails(report) {
    const currency =
      report.meta?.currency || "VND"

    const rankingColumns = [
      {
        label: "#",
        render: (_row, index) =>
          String(index + 1),
      },
      {
        label: "Nhân viên",
        render: (row) => `
          <strong>
            ${escapeHtml(
              row.employee_name
              || row.employee
              || "Unassigned",
            )}
          </strong>

          <div class="crm-reports-muted">
            ${escapeHtml(
              [
                row.team,
                row.territory,
              ]
                .filter(Boolean)
                .join(" · "),
            )}
          </div>
        `,
      },
      {
        label: "Open",
        render: (row) =>
          formatNumber(
            row.open_deals,
          ),
      },
      {
        label: "Won / Lost",
        render: (row) =>
          `${formatNumber(
            row.won_deals,
          )} / ${formatNumber(
            row.lost_deals,
          )}`,
      },
      {
        label: "Doanh thu",
        render: (row) =>
          formatCurrency(
            row.revenue,
            currency,
          ),
      },
      {
        label: "Win Rate",
        render: (row) =>
          `${formatNumber(
            row.win_rate,
          )}%`,
      },
      {
        label: "Thời gian chốt",
        render: (row) => `
          ${formatNumber(
            row.average_closing_days,
          )} ngày

          <div class="crm-reports-muted">
            Team:
            ${formatNumber(
              row
                .team_average_closing_days,
            )} ngày
          </div>
        `,
      },
      {
        label: "Xu hướng",
        render: (row) =>
          formatPercent(
            row.trend_percent,
          ),
      },
      {
        label: "Stale",
        render: (row) =>
          formatNumber(
            row.stale_deals,
          ),
      },
    ]

    function dimensionColumns(
      key,
      label,
    ) {
      return [
        {
          label,
          render: (row) =>
            escapeHtml(row[key]),
        },
        {
          label: "Tổng Deal",
          render: (row) =>
            formatNumber(
              row.total_deals,
            ),
        },
        {
          label: "Won / Lost",
          render: (row) =>
            `${formatNumber(
              row.won_deals,
            )} / ${formatNumber(
              row.lost_deals,
            )}`,
        },
        {
          label: "Conversion",
          render: (row) =>
            `${formatNumber(
              row.conversion_rate,
            )}%`,
        },
        {
          label: "Doanh thu",
          render: (row) =>
            formatCurrency(
              row.revenue,
              currency,
            ),
        },
      ]
    }

    const funnelColumns = [
      {
        label: "Giai đoạn",
        render: (row) =>
          escapeHtml(row.stage),
      },
      {
        label: "Số Deal",
        render: (row) =>
          formatNumber(
            row.deal_count,
          ),
      },
      {
        label: "Drop-off",
        render: (row) =>
          `${formatNumber(
            row.drop_off_percent,
          )}%`,
      },
    ]

    const forecastColumns = [
      {
        label: "Tháng",
        render: (row) =>
          escapeHtml(row.month),
      },
      {
        label: "Số Deal",
        render: (row) =>
          formatNumber(
            row.deal_count,
          ),
      },
      {
        label: "Pipeline",
        render: (row) =>
          formatCurrency(
            row.pipeline_value,
            currency,
          ),
      },
      {
        label: "Weighted Revenue",
        render: (row) =>
          formatCurrency(
            row.weighted_revenue,
            currency,
          ),
      },
    ]

    const risks =
      report.risks || {}

    return `
      ${warningsHtml(
        report.meta?.warnings,
      )}

      ${sectionHtml(
        "Bảng xếp hạng nhân viên",
        tableHtml(
          rankingColumns,
          report.employee_ranking || [],
        ),
      )}

      <div class="crm-reports-two-columns">
        ${sectionHtml(
          "Phân tích Lead Source",
          tableHtml(
            dimensionColumns(
              "source",
              "Lead Source",
            ),
            report.source_analysis || [],
          ),
        )}

        ${sectionHtml(
          "Phân tích Territory",
          tableHtml(
            dimensionColumns(
              "territory",
              "Territory",
            ),
            report.territory_analysis
            || [],
          ),
        )}
      </div>

      <div class="crm-reports-two-columns">
        ${sectionHtml(
          "Funnel và Drop-off",
          tableHtml(
            funnelColumns,
            report.funnel || [],
          ),
        )}

        ${sectionHtml(
          "Forecast doanh thu",
          tableHtml(
            forecastColumns,
            report.forecast || [],
          ),
        )}
      </div>

      <div class="crm-reports-three-columns">
        ${sectionHtml(
          "Deal trì trệ",
          actionListHtml(
            risks.stale_deals || [],
            currency,
          ),
        )}

        ${sectionHtml(
          "Deal quá hạn",
          actionListHtml(
            risks.overdue_deals || [],
            currency,
          ),
        )}

        ${sectionHtml(
          "Deal lớn sắp đóng",
          actionListHtml(
            risks
              .high_value_closing_soon
            || [],
            currency,
          ),
        )}
      </div>
    `
  }

  function employeeDetails(report) {
    const currency =
      report.meta?.currency || "VND"

    const overview =
      report.overview || {}

    const actions =
      report.actions || {}

    const trendColumns = [
      {
        label: "Tháng",
        render: (row) =>
          escapeHtml(row.month),
      },
      {
        label: "Opened",
        render: (row) =>
          formatNumber(row.opened),
      },
      {
        label: "Won",
        render: (row) =>
          formatNumber(row.won),
      },
      {
        label: "Lost",
        render: (row) =>
          formatNumber(row.lost),
      },
      {
        label: "Doanh thu",
        render: (row) =>
          formatCurrency(
            row.revenue,
            currency,
          ),
      },
      {
        label: "Chốt trung bình",
        render: (row) =>
          `${formatNumber(
            row.average_closing_days,
          )} ngày`,
      },
    ]

    const pipelineColumns = [
      {
        label: "Giai đoạn",
        render: (row) =>
          escapeHtml(row.stage),
      },
      {
        label: "Số Deal",
        render: (row) =>
          formatNumber(
            row.deal_count,
          ),
      },
    ]

    const benchmark = `
      <div class="crm-reports-benchmark-grid">
        <div>
          <span>Xếp hạng cá nhân</span>

          <strong>
            #${formatNumber(
              overview.rank,
            )}/${formatNumber(
              overview.team_size,
            )}
          </strong>
        </div>

        <div>
          <span>Win Rate</span>

          <strong>
            ${formatNumber(
              overview.win_rate,
            )}%
          </strong>
        </div>

        <div>
          <span>Thời gian chốt của tôi</span>

          <strong>
            ${formatNumber(
              overview
                .average_closing_days,
            )} ngày
          </strong>
        </div>

        <div>
          <span>Trung bình team</span>

          <strong>
            ${formatNumber(
              overview
                .team_average_closing_days,
            )} ngày
          </strong>
        </div>
      </div>
    `

    return `
      ${warningsHtml(
        report.meta?.warnings,
      )}

      ${sectionHtml(
        "Hiệu suất cá nhân so với team",
        benchmark,
      )}

      <div class="crm-reports-three-columns">
        ${sectionHtml(
          "Follow-up đến hạn",
          actionListHtml(
            actions.follow_up_due || [],
            currency,
          ),
        )}

        ${sectionHtml(
          "Deal trì trệ",
          actionListHtml(
            actions.stale_deals || [],
            currency,
          ),
        )}

        ${sectionHtml(
          "Deal sắp đóng",
          actionListHtml(
            actions.closing_soon || [],
            currency,
          ),
        )}
      </div>

      <div class="crm-reports-two-columns">
        ${sectionHtml(
          "Xu hướng cá nhân",
          tableHtml(
            trendColumns,
            report.trends || [],
          ),
        )}

        ${sectionHtml(
          "Pipeline cá nhân",
          tableHtml(
            pipelineColumns,
            report.pipeline || [],
          ),
        )}
      </div>
    `
  }

  function renderDetails(report) {
    const root =
      ensureDetailsRoot()

    if (!root) {
      return
    }

    root.innerHTML =
      report.view_mode === "manager"
        ? managerDetails(report)
        : employeeDetails(report)
  }

  async function loadExtension() {
    if (
      !isDashboardRoute() ||
      loading
    ) {
      return
    }

    const toolbarRoot =
      ensureToolbarRoot()

    const detailsRoot =
      ensureDetailsRoot()

    if (
      !toolbarRoot ||
      !detailsRoot
    ) {
      return
    }

    loading = true

    document
      .getElementById(MARKER_ID)
      ?.remove()

    toolbarRoot.innerHTML = `
      <div class="crm-reports-loading">
        Đang tải bộ lọc nâng cao…
      </div>
    `

    detailsRoot.innerHTML = `
      <div class="crm-reports-loading">
        Đang tải báo cáo chi tiết…
      </div>
    `

    try {
      const params =
        getCurrentReportParams()

      const report =
        await callReport(params)

      let optionsReport = report

      if (
        report.meta?.can_switch_view
      ) {
        optionsReport =
          await callReport({
            from_date:
              params.from_date,

            to_date:
              params.to_date,

            view_mode: "manager",
          })
      }

      renderToolbar(
        report,
        optionsReport,
      )

      renderDetails(report)
    } catch (error) {
      console.error(
        "[crm_reports] Extension error",
        error,
      )

      detailsRoot.innerHTML = `
        <div class="crm-reports-error">
          Không thể tải báo cáo chi tiết.

          <div>
            ${escapeHtml(
              error.message || error,
            )}
          </div>
        </div>
      `
    } finally {
      loading = false
    }
  }

  function scheduleReload(
    delay = 250,
  ) {
    window.clearTimeout(
      reloadTimer,
    )

    reloadTimer =
      window.setTimeout(
        loadExtension,
        delay,
      )
  }

  window.addEventListener(
    "crm-reports:dashboard-request",
    () => scheduleReload(350),
  )

  window.addEventListener(
    "popstate",
    () => scheduleReload(250),
  )

  const originalPushState =
    history.pushState

  const originalReplaceState =
    history.replaceState

  history.pushState = function (
    ...args
  ) {
    const result =
      originalPushState.apply(
        this,
        args,
      )

    scheduleReload(250)

    return result
  }

  history.replaceState = function (
    ...args
  ) {
    const result =
      originalReplaceState.apply(
        this,
        args,
      )

    scheduleReload(250)

    return result
  }

  const observer =
    new MutationObserver(() => {
      if (
        isDashboardRoute() &&
        (
          !document.getElementById(
            TOOLBAR_ID,
          ) ||
          !document.getElementById(
            DETAILS_ID,
          )
        )
      ) {
        scheduleReload(300)
      }
    })

  observer.observe(
    document.documentElement,
    {
      childList: true,
      subtree: true,
    },
  )

  scheduleReload(300)

  console.info(
    "[crm_reports] full extension loaded",
  )
})()