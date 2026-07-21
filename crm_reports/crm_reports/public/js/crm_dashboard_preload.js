;(function () {
  "use strict"

  const STORAGE_KEY =
    "crm_reports_dashboard_filters_v1"

  const DASHBOARD_METHOD =
    "/api/method/crm.api.dashboard.get_dashboard"

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

  function readFilters() {
    try {
      const raw =
        window.localStorage.getItem(
          STORAGE_KEY,
        )

      return raw
        ? JSON.parse(raw)
        : {}
    } catch (error) {
      console.error(
        "[crm_reports] Cannot read filters",
        error,
      )

      return {}
    }
  }

  function writeFilters(filters) {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(filters || {}),
    )
  }

  function announceRequest(params) {
    window.__crmReportsLastDashboardParams = {
      ...params,
    }

    window.dispatchEvent(
      new CustomEvent(
        "crm-reports:dashboard-request",
        {
          detail: {
            ...params,
          },
        },
      ),
    )
  }

  function applyCustomFilters(params) {
    const result = {
      ...(params || {}),
    }

    const customFilters = readFilters()

    const filterNames = [
      "team",
      "source",
      "territory",
      "status",
    ]

    filterNames.forEach((fieldname) => {
      const value = cleanValue(
        customFilters[fieldname],
      )

      if (value) {
        result[fieldname] = value
      } else {
        delete result[fieldname]
      }
    })

    announceRequest(result)

    return result
  }

  function isDashboardRequest(url) {
    return String(url || "").includes(
      DASHBOARD_METHOD,
    )
  }

  function assignSearchParams(url, params) {
    url.search = ""

    Object.entries(params).forEach(
      ([key, value]) => {
        const cleaned = cleanValue(value)

        if (cleaned) {
          url.searchParams.set(
            key,
            cleaned,
          )
        }
      },
    )

    return url
  }

  function patchStringBody(body) {
    const trimmed = String(
      body || "",
    ).trim()

    if (!trimmed) {
      return JSON.stringify(
        applyCustomFilters({}),
      )
    }

    if (trimmed.startsWith("{")) {
      try {
        const parsed = JSON.parse(trimmed)

        if (
          parsed.params &&
          typeof parsed.params === "object"
        ) {
          parsed.params =
            applyCustomFilters(
              parsed.params,
            )

          return JSON.stringify(parsed)
        }

        return JSON.stringify(
          applyCustomFilters(parsed),
        )
      } catch (error) {
        console.error(
          "[crm_reports] Invalid JSON body",
          error,
        )
      }
    }

    try {
      const source =
        new URLSearchParams(trimmed)

      const params =
        Object.fromEntries(
          source.entries(),
        )

      const updated =
        applyCustomFilters(params)

      const result =
        new URLSearchParams()

      Object.entries(updated).forEach(
        ([key, value]) => {
          const cleaned =
            cleanValue(value)

          if (cleaned) {
            result.set(key, cleaned)
          }
        },
      )

      return result.toString()
    } catch (error) {
      console.error(
        "[crm_reports] Cannot patch body",
        error,
      )

      return body
    }
  }

  function patchBody(body) {
    if (body instanceof URLSearchParams) {
      const params =
        Object.fromEntries(
          body.entries(),
        )

      const updated =
        applyCustomFilters(params)

      const result =
        new URLSearchParams()

      Object.entries(updated).forEach(
        ([key, value]) => {
          const cleaned =
            cleanValue(value)

          if (cleaned) {
            result.set(key, cleaned)
          }
        },
      )

      return result
    }

    if (body instanceof FormData) {
      const params = {}

      body.forEach((value, key) => {
        params[key] = value
      })

      const updated =
        applyCustomFilters(params)

      const result = new FormData()

      Object.entries(updated).forEach(
        ([key, value]) => {
          const cleaned =
            cleanValue(value)

          if (cleaned) {
            result.set(key, cleaned)
          }
        },
      )

      return result
    }

    if (
      typeof body === "string" ||
      body === null ||
      body === undefined
    ) {
      return patchStringBody(body)
    }

    return body
  }

  /*
   * Patch Fetch API.
   */
  const originalFetch =
    window.fetch.bind(window)

  window.fetch = function patchedFetch(
    input,
    init = {},
  ) {
    const requestUrl =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input?.url

    if (!isDashboardRequest(requestUrl)) {
      return originalFetch(input, init)
    }

    const method = String(
      init.method ||
        input?.method ||
        "GET",
    ).toUpperCase()

    if (method === "GET") {
      const url = new URL(
        requestUrl,
        window.location.origin,
      )

      const params =
        Object.fromEntries(
          url.searchParams.entries(),
        )

      const updated =
        applyCustomFilters(params)

      assignSearchParams(
        url,
        updated,
      )

      if (input instanceof Request) {
        const patchedRequest =
          new Request(
            url.toString(),
            input,
          )

        return originalFetch(
          patchedRequest,
          init,
        )
      }

      return originalFetch(
        url.toString(),
        init,
      )
    }

    const patchedInit = {
      ...init,
      body: patchBody(init.body),
    }

    return originalFetch(
      input,
      patchedInit,
    )
  }

  /*
   * Patch XMLHttpRequest để dự phòng
   * trường hợp Frappe UI không dùng fetch.
   */
  const originalOpen =
    XMLHttpRequest.prototype.open

  const originalSend =
    XMLHttpRequest.prototype.send

  XMLHttpRequest.prototype.open =
    function patchedOpen(
      method,
      url,
      ...rest
    ) {
      this.__crmReportsMethod =
        String(
          method || "GET",
        ).toUpperCase()

      this.__crmReportsUrl =
        String(url || "")

      let finalUrl = url

      if (
        isDashboardRequest(url) &&
        this.__crmReportsMethod === "GET"
      ) {
        const parsedUrl = new URL(
          url,
          window.location.origin,
        )

        const params =
          Object.fromEntries(
            parsedUrl.searchParams.entries(),
          )

        const updated =
          applyCustomFilters(params)

        assignSearchParams(
          parsedUrl,
          updated,
        )

        finalUrl =
          parsedUrl.toString()
      }

      return originalOpen.call(
        this,
        method,
        finalUrl,
        ...rest,
      )
    }

  XMLHttpRequest.prototype.send =
    function patchedSend(body) {
      if (
        isDashboardRequest(
          this.__crmReportsUrl,
        ) &&
        this.__crmReportsMethod !== "GET"
      ) {
        body = patchBody(body)
      }

      return originalSend.call(
        this,
        body,
      )
    }

  window.CRMReportsFilters = {
    read: readFilters,

    write(filters) {
      writeFilters(filters)
    },

    clear() {
      window.localStorage.removeItem(
        STORAGE_KEY,
      )
    },
  }

  window.__crmReportsPreloadLoaded = true

  console.info(
    "[crm_reports] preload loaded",
  )
})()