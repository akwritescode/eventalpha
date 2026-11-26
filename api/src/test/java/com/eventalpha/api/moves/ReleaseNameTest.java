package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

class ReleaseNameTest {

    /** Every title the calendar loader keeps (src/eventalpha/calendars.py), plus the FOMC rows. */
    private static final List<String> TRACKED = List.of(
            "Employment Situation", "Consumer Price Index", "Producer Price Index",
            "Job Openings and Labor Turnover Survey", "Employment Cost Index", "U.S. Import and Export Price Indexes",
            "Real Earnings", "Productivity and Costs", "Gross Domestic Product", "Personal Income and Outlays",
            "Advance Monthly Sales for Retail and Food Services", "Unemployment Insurance Weekly Claims Report",
            "Industrial Production and Capacity Utilization", "New Residential Construction", "Surveys of Consumers",
            "Manufacturers' Shipments, Inventories, and Orders", "ADP National Employment Report",
            "FOMC rate decision", "FOMC rate decision + projections");

    @Test
    void summaryNamesNeverContainAPeriod() {
        // The web app strips the "Economic calendar: ..." sentence at its first full stop.
        for (String title : TRACKED) {
            assertThat(MoveRepository.releaseName(title)).as(title).doesNotContain(".");
        }
        assertThat(MoveRepository.releaseName("U.S. Import and Export Price Indexes")).isEqualTo("import prices");
        assertThat(MoveRepository.releaseName("A New Release for Oct. 2026")).isEqualTo("A New Release for Oct 2026");
    }
}
