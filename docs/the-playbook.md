This playbook is designed to systematically filter publicly disclosed insider trading data to identify transactions that exhibit high conviction and suggest opportunistic buying, thereby differentiating "signal" from "noise". Academic studies suggest that tracking insider purchases tends to outperform the general market.

## The Insider Trade Filtering Playbook

### I. Setup and Automated Tracking Tools

Use automated tools and screening services to capture and process required public disclosures, typically **SEC Form 4 filings** (which must be filed within three business days of a trade).

| Step | Action and Tool Use | Rationale and Sources |
| :--- | :--- | :--- |
| **1. Data Aggregation** | Utilize websites like **Open Insider** and **SEC Form4.com**, which pull data from the **SEC Edgar database** and weed out some uninformative reports. | Automated data mining is essential for managing the vast amount of trading data. |
| **2. Automated Alerts** | Set up automated alerts for **new SEC filings** related to specific companies or portfolios. | Features like Perplexity Task can schedule deep research reports to create an **AI agent** that tracks corporate insider buying. |
| **3. Screening Implementation** | Use specialized screening tools (e.g., GuruFocus) to apply filters. Scan for transactions in the last **30 to 45 days** . | Technology allows for far accelerated analysis of suspicious trading patterns. |

---

### II. Quantitative Filters (Conviction and Size)

The size of the purchase must be significant relative to the stock, demonstrating the insider is putting "skin in the game".

| Criteria | Recommended Filter | Rationale and Sources |
| :--- | :--- | :--- |
| **Absolute Value** | Focus on transactions of e.g. **$200,000 or more**. The minimum cutoff should be at least **$100,000**. | Ignore insignificant transactions below $5,000 to $15,000, which may be routine 401k contributions. $25,000 is generally considered too low. |
| **Relative Position Size** | Look for trades that represent an increase of **20% to 50%** in the insider’s current holdings . | A large shareholder increasing their stake by only 0.5% shows low conviction, regardless of the dollar size . |
| **Relative Wealth** | Consider the purchase size relative to the insider's salary or net worth. | If an executive invests the equivalent of their entire annual salary, it signals high conviction. A multi-million dollar buy by a billionaire may not be significant if it is a tiny percentage of their wealth. |

---

### III. Qualitative Filters (Consensus and Position)

The identity of the buyer and the level of consensus among executives are primary determinants of signal strength.

#### A. The Power of Cluster Buys (Consensus)

| Criteria | Recommended Filter | Rationale and Sources |
| :--- | :--- | :--- |
| **Cluster Buys** | Identify when **multiple insiders buy simultaneously** (cluster buys). | This is a primary signal suggesting consensus that the stock may be undervalued. |
| **Quantity** | Filter for transactions involving **two or more insiders buying**. **Three or four or more insiders buying is preferred**. | Consensus minimizes the impact of individual biases or poor timing. |

#### B. Informational Weight by Position

Focus filtering on key officers using automated criteria like **Insider Title**.

| Insider Position | Informational Weight | Rationale and Sources |
| :--- | :--- | :--- |
| **Chief Financial Officer (CFO)** | **Highest Weight** | They are intimately connected with company financials, liabilities, and are often valuation-conscious. |
| **General Counsel** | **High Weight** | Their decision to buy suggests strong expectations of gains, as they are typically risk-averse. |
| **Vice Presidents / COO / CMO** | **Good Weight** | They are familiar with specific operational aspects like product success or supply chain issues. |
| **Chief Executive Officer (CEO)** | **Mixed Weight** | One perspective views them as the best person to follow due to day-to-day involvement and knowledge of internal health. However, they are often prone to buying as a "sign of faith" and can sometimes be disconnected from valuation, earning a lower weight. |
| **Directors** | **Lower Weight** | They are more removed from daily operations, meeting about once a quarter, making their trades less informative than C-suite executives. |

---

### IV. Contextual and Timing Filters

The context of *when* the buying occurs determines if the trade is opportunistic.

| Criteria | Actionable Insight | Rationale and Sources |
| :--- | :--- | :--- |
| **Infrequent Activity** | Look for companies that do **not** normally see routine insider buying but suddenly experience a **spike in volume**. | This suggests something significant could be happening that triggered the unusual activity . |
| **First-Time Buyer** | Look for insiders (e.g., directors, employees) who have been with the company for **two to five-plus years** but are making their first purchase. | This implies a high-conviction decision based on specific knowledge. |
| **Buying Off the Lows** | Identify heavy buying when the stock or market is crashing or during a "moment of distress". | This indicates well-timed, opportunistic trades, as insiders know the company's long-term viability . |
| **Buying Near Highs** | Look for insiders buying when the stock is near its multi-year highs (e.g., within 5-15%) . | This suggests they anticipate strong news that will drive the price even higher . |
| **Transaction Type** | Ensure transactions are **open market purchases**. | Avoid new share offerings where the purchase may be required by investors to ensure "skin in the game". |

---

### V. Filtering Out Noise (What to Avoid)

Remove transactions that look like buys but lack predictive power or are mandatory disclosures.

| Noise Signal | Rationale for Avoidance | Sources |
| :--- | :--- | :--- |
| **Option Exercises** | Avoid transactions marked as Code **'M'** (derivative securities) . This is cashing out compensation, not a new opportunistic trade, and often shows up as a simultaneous buy and sell . | |
| **Fund/10% Owner Activity** | Disregard trades made by large institutional funds or ETFs (often listed as 10% owners). | Their buying is often for portfolio rebalancing or fundamental alignment and is less informed than C-suite executive trades. |
| **New Executive Buys** | Discount "show of faith" purchases made by newly appointed C-level executives within their first few months . |  |
| **Poor Track Record** | Discount the current buy signal if the insider has a history of poorly timed trades or losing money over several years . |  |
| **Routine Selling** | Insider **selling** is generally harder to interpret due to various personal reasons (e.g., tuition, diversification, retirement) . | Focus instead on **cluster selling** that is "very unusual," which strongly implies the stock is overvalued and is a signal to exit . |

***

### Conclusion: Due Diligence

Even after applying these rigorous filters, it is crucial not to follow insiders **blindly** . Insiders are focused on long-term business goals and are "not always great timers" in the short term . Additional due diligence is always required before investing .

***

**Analogy:** Filtering for good insider trades is like panning for gold. Most of the material you sift through is gravel and river water (routine trades, option exercises, small buys, and fund activity). The strict filters (minimum size, cluster buys, informed positions) are the specific screens you use, ensuring you only hold onto the few high-density nuggets (opportunistic, high-conviction purchases) that suggest real value is buried nearby.
