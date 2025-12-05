import { useEffect, useState } from "react";
import axios from "axios";

const API_BASE = "http://localhost:8000";

function App() {
  const [tasks, setTasks] = useState([]);
  const [todayPlan, setTodayPlan] = useState(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [clearLoading, setClearLoading] = useState(false);
  const [llmCommand, setLlmCommand] = useState("");
  const [llmResult, setLlmResult] = useState(null);
  const [error, setError] = useState("");

  // Load tasks once
  useEffect(() => {
    axios
      .get(`${API_BASE}/tasks`)
      .then((res) => setTasks(res.data))
      .catch((err) => {
        console.error(err);
        setError("Failed to load tasks from backend.");
      });
  }, []);

  // Load today's plan
  const fetchTodayPlan = async () => {
    try {
      setLoadingPlan(true);
      setError("");
      const res = await axios.get(`${API_BASE}/today_plan`);
      setTodayPlan(res.data);
    } catch (err) {
      console.error(err);
      setError("Failed to load today's plan.");
    } finally {
      setLoadingPlan(false);
    }
  };

  useEffect(() => {
    fetchTodayPlan();
  }, []);

  const handleScheduleRange = async (days = 7) => {
    try {
      setScheduleLoading(true);
      setError("");
      const payload = {
        start_date: null, // backend treats null as today
        days,
        allow_reschedule: true,
      };
      const res = await axios.post(`${API_BASE}/schedule`, payload);
      await fetchTodayPlan();
      setLlmResult(res.data);
    } catch (err) {
      console.error(err);
      setError("Failed to schedule range.");
    } finally {
      setScheduleLoading(false);
    }
  };

  const handleClearRange = async (days = 7) => {
    try {
      setClearLoading(true);
      setError("");
      const payload = {
        start_date: null, // today
        days,
      };
      const res = await axios.post(`${API_BASE}/clear`, payload);
      await fetchTodayPlan();
      setLlmResult(res.data);
    } catch (err) {
      console.error(err);
      setError("Failed to clear range.");
    } finally {
      setClearLoading(false);
    }
  };

  const handleLlmCommand = async (e) => {
    e.preventDefault();
    if (!llmCommand.trim()) return;
    try {
      setError("");
      setLlmResult(null);
      const res = await axios.post(`${API_BASE}/command_llm`, {
        command: llmCommand,
      });
      setLlmResult(res.data);
      setLlmCommand(""); // clear textarea
      await fetchTodayPlan();
    } catch (err) {
      console.error(err);
      setError("Failed to send LLM command.");
    }
  };

  const statusColor = (status) => {
    if (status === "scheduled") return "#15803d"; // green
    if (status === "scheduled_rescheduled") return "#c2410c"; // orange
    if (status === "skipped") return "#b91c1c"; // red
    return "#374151";
  };

  return (
    <div style={styles.app}>
      <div style={styles.container}>
     <header style={styles.header}>
        <h1 style={styles.title}>AI Calendar Agent Dashboard</h1>
        <p style={styles.subtitle}>
          Autonomous routine scheduling • Conflict-aware • LLM-controlled
        </p>
      </header>

      {error && <div style={styles.error}>{error}</div>}

      <main style={styles.main}>
        {/* LEFT: controls */}
        <section style={styles.leftColumn}>
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Controls</h2>
            <p style={styles.helpText}>
              Trigger your agent to schedule or clear your routine.
            </p>
            <div style={styles.buttonRow}>
              <button
                style={styles.primaryButton}
                onClick={() => handleScheduleRange(7)}
                disabled={scheduleLoading}
              >
                {scheduleLoading ? "Scheduling..." : "Schedule next 7 days"}
              </button>
              <button
                style={styles.secondaryButton}
                onClick={() => handleScheduleRange(30)}
                disabled={scheduleLoading}
              >
                {scheduleLoading ? "Scheduling..." : "Schedule next 30 days"}
              </button>
            </div>
            <div style={styles.buttonRow}>
              <button
                style={styles.dangerButton}
                onClick={() => handleClearRange(7)}
                disabled={clearLoading}
              >
                {clearLoading ? "Clearing..." : "Clear next 7 days"}
              </button>
            </div>
          </div>

          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Natural-language Command</h2>
            <p style={styles.helpText}>Let the LLM decide what to do. Try:</p>
            <ul style={styles.exampleList}>
              <li>"schedule my routine for the next 5 days"</li>
              <li>"clear the next 7 days"</li>
              <li>"just schedule today"</li>
              <li>"schedule the next 3 days without rescheduling"</li>
            </ul>
            <form onSubmit={handleLlmCommand}>
              <textarea
                style={styles.textarea}
                rows={3}
                placeholder="Type your command here..."
                value={llmCommand}
                onChange={(e) => setLlmCommand(e.target.value)}
              />
              <button style={styles.primaryButton} type="submit">
                Send to Agent
              </button>
            </form>
          </div>

          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Configured Tasks</h2>
            <p style={styles.helpText}>Loaded from daily_fixed_tasks.json</p>
            <ul style={styles.taskList}>
              {tasks.map((t) => (
                <li key={t.name} style={styles.taskItem}>
                  <strong>{t.name}</strong> — {t.start_time} ({t.duration_minutes}{" "}
                  min) · {t.days.join(", ")}
                </li>
              ))}
              {tasks.length === 0 && <li>No tasks loaded.</li>}
            </ul>
          </div>
        </section>

        {/* RIGHT: today's plan + last agent response */}
        <section style={styles.rightColumn}>
          <div style={styles.card}>
            <div style={styles.cardHeaderRow}>
              <h2 style={styles.cardTitle}>Today&apos;s Plan</h2>
              <button
                style={styles.smallButton}
                onClick={fetchTodayPlan}
                disabled={loadingPlan}
              >
                {loadingPlan ? "Refreshing..." : "Refresh"}
              </button>
            </div>
            {todayPlan ? (
              <>
                <p style={styles.helpText}>Date: {todayPlan.date}</p>
                <div style={{ overflowX: "auto" }}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th>Task</th>
                        <th>Status</th>
                        <th>Start</th>
                        <th>End</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {todayPlan.decisions.map((d, idx) => (
                        <tr key={idx}>
                          <td>{d.task_name}</td>
                          <td style={{ color: statusColor(d.status) }}>
                            {d.status}
                          </td>
                          <td>{d.scheduled_start || "-"}</td>
                          <td>{d.scheduled_end || "-"}</td>
                          <td>{d.reason || ""}</td>
                        </tr>
                      ))}
                      {todayPlan.decisions.length === 0 && (
                        <tr>
                          <td
                            colSpan={5}
                            style={{
                              textAlign: "center",
                              color: "#6b7280",
                              padding: "0.5rem",
                            }}
                          >
                            No tasks scheduled for today (maybe your routine
                            skips this day).
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p style={styles.helpText}>Loading today&apos;s plan...</p>
            )}
          </div>

          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Last Agent Response</h2>
            <p style={styles.helpText}>
              Raw JSON from /schedule, /clear, or /command_llm
            </p>
            <pre style={styles.pre}>
              {llmResult ? JSON.stringify(llmResult, null, 2) : "No actions yet."}
            </pre>
          </div>
        </section>
      </main>
      </div>
     
    </div>
  );
}

// ---------- Styles ----------

const styles = {
  app: {
    minHeight: "100vh",
      margin: "0 auto",
    backgroundColor: "#f9fafb",
    padding: "1.5rem 2rem",
    color: "#111827",
    fontFamily:
      "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  container: {
  maxWidth: "1200px",      // controls total width of the app
  margin: "0 auto",        // centers the entire UI
},
  header: {
    marginBottom: "1.5rem",
  },
  title: {
    margin: 0,
    fontSize: "1.8rem",
    fontWeight: 700,
    color: "#111827",
  },
  subtitle: {
    margin: 0,
    marginTop: "0.4rem",
    color: "#6b7280",
    fontSize: "0.95rem",
  },
  main: {
    display: "grid",
    gridTemplateColumns: "1.05fr 1.35fr",
    gap: "1.5rem",
    alignItems: "flex-start",
  },
  leftColumn: {
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
  },
  rightColumn: {
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
  },
  card: {
    backgroundColor: "#ffffff",
    borderRadius: "0.75rem",
    padding: "1rem 1.25rem",
    boxShadow: "0 10px 15px -3px rgba(15, 23, 42, 0.06)",
    border: "1px solid #e5e7eb",
  },
  cardTitle: {
    margin: 0,
    fontSize: "1.05rem",
    fontWeight: 600,
    color: "#111827",
  },
  cardHeaderRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "0.5rem",
  },
  helpText: {
    fontSize: "0.85rem",
    color: "#6b7280",
    marginBottom: "0.75rem",
    marginTop: "0.4rem",
  },
  buttonRow: {
    display: "flex",
    gap: "0.5rem",
    marginBottom: "0.5rem",
    flexWrap: "wrap",
  },
  primaryButton: {
    backgroundColor: "#2563eb",
    color: "#ffffff",
    border: "none",
    borderRadius: "9999px",
    padding: "0.5rem 1rem",
    cursor: "pointer",
    fontSize: "0.88rem",
  },
  secondaryButton: {
    backgroundColor: "#0f766e",
    color: "#ffffff",
    border: "none",
    borderRadius: "9999px",
    padding: "0.5rem 1rem",
    cursor: "pointer",
    fontSize: "0.88rem",
  },
  dangerButton: {
    backgroundColor: "#b91c1c",
    color: "#ffffff",
    border: "none",
    borderRadius: "9999px",
    padding: "0.5rem 1rem",
    cursor: "pointer",
    fontSize: "0.88rem",
  },
  smallButton: {
    backgroundColor: "#e5e7eb",
    color: "#374151",
    border: "1px solid #d1d5db",
    borderRadius: "9999px",
    padding: "0.25rem 0.75rem",
    cursor: "pointer",
    fontSize: "0.78rem",
  },
  textarea: {
    width: "100%",
    padding: "0.5rem",
    borderRadius: "0.5rem",
    border: "1px solid #d1d5db",
    marginBottom: "0.5rem",
    fontFamily: "inherit",
    fontSize: "0.9rem",
    resize: "vertical",
  },
  taskList: {
    listStyle: "none",
    paddingLeft: 0,
    maxHeight: "200px",
    overflowY: "auto",
    margin: 0,
  },
  taskItem: {
    marginBottom: "0.25rem",
    fontSize: "0.85rem",
    color: "#111827",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "0.82rem",
    border: "1px solid #e5e7eb",
  },
  pre: {
    backgroundColor: "#f3f4f6",
    color: "#111827",
    padding: "0.75rem",
    borderRadius: "0.5rem",
    maxHeight: "260px",
    overflow: "auto",
    fontSize: "0.8rem",
    border: "1px solid #e5e7eb",
  },
  error: {
    backgroundColor: "#fee2e2",
    color: "#b91c1c",
    padding: "0.75rem 1rem",
    borderRadius: "0.5rem",
    marginBottom: "1rem",
    border: "1px solid #fecaca",
    fontSize: "0.9rem",
  },
  exampleList: {
    fontSize: "0.8rem",
    color: "#4b5563",
    marginTop: 0,
    paddingLeft: "1.1rem",
  },
};

export default App;
