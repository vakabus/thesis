//! In this experiment
//!
use clap::Parser;

use crate::utils::ovs::{get_ovs_dpctl_show, OVSStats};
use std::{
    sync::{Arc, Mutex},
    thread::{self, sleep},
    time::{Duration, Instant},
};

use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use std::io;
use tui::{
    backend::{Backend, CrosstermBackend},
    layout::{Constraint, Layout},
    style::{Modifier, Style},
    widgets::{Block, Borders, Cell, Row, Table, TableState},
    Frame, Terminal,
};

#[derive(Parser, Debug)]
pub struct MonitorArgs {
    /// refresh interval
    #[arg(short, long, default_value_t = 200)]
    interval_ms: u64,
}

pub fn run(args: MonitorArgs) {
    // setup terminal
    enable_raw_mode().unwrap();
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture).unwrap();
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend).unwrap();

    // create app and run it
    let app = App::new(args);
    let res = run_app(&mut terminal, app);

    // restore terminal
    disable_raw_mode().unwrap();
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )
    .unwrap();
    terminal.show_cursor().unwrap();

    if let Err(err) = res {
        println!("{:?}", err)
    }
}

struct Stats {
    ovs: OVSStats,
}

struct App {
    state: TableState,
    data: Arc<Mutex<Option<Stats>>>,
    args: MonitorArgs,
}

impl App {
    fn new(args: MonitorArgs) -> App {
        let r = App {
            state: TableState::default(),
            data: Arc::new(Mutex::new(None)),
            args,
        };

        r.start_collecting();

        r
    }

    fn start_collecting(&self) {
        let data = self.data.clone();
        let interval = Duration::from_millis(self.args.interval_ms);

        let _handle = thread::spawn(move || {
            let program_start = Instant::now();
            loop {
                let new_stats = get_ovs_dpctl_show(program_start);
                let _old_stats = match new_stats {
                    Ok(new_stats) => data.lock().unwrap().replace(Stats { ovs: new_stats }),
                    // we can't do much about errors
                    Err(e) => {
                        warn!("error getting ovs dp stats: {:?}", e);
                        data.lock().unwrap().take()
                    },
                };

                sleep(interval);
            }
        });
    }
}

fn run_app<B: Backend>(terminal: &mut Terminal<B>, mut app: App) -> io::Result<()> {
    // let's update the UI 10x per second (note: it is different interval than what data collection does)
    let interval = Duration::from_millis(100);

    loop {
        terminal.draw(|f| ui(f, &mut app))?;

        if event::poll(interval)? {
            if let Event::Key(key) = event::read()? {
                match key.code {
                    KeyCode::Char('q') => return Ok(()),
                    //KeyCode::Down => app.next(),
                    //KeyCode::Up => app.previous(),
                    _ => {}
                }
            }
        }
    }
}

fn ui<B: Backend>(f: &mut Frame<B>, app: &mut App) {
    let rects = Layout::default()
        .constraints([Constraint::Percentage(100)].as_ref())
        .margin(0)
        .split(f.size());

    // header
    let reversed_style = Style::default().add_modifier(Modifier::REVERSED);
    let header_cells = ["Name", "Value", "Unit"]
        .iter()
        .map(|h| Cell::from(*h).style(Style::default().add_modifier(Modifier::REVERSED)));
    let header = Row::new(header_cells)
        .style(reversed_style)
        .height(1)
        .bottom_margin(0);

    // data
    let items = {
        let stats = app.data.lock().unwrap();
        vec![
            (
                "Flows installed in kernel",
                format!("{:?}", stats.as_ref().map(|s| s.ovs.flows)),
            ),
            (
                "Lookup hits",
                format!("{:?}", stats.as_ref().map(|s| s.ovs.lookup_hit)),
            ),
            (
                "Lookup lost",
                format!("{:?}", stats.as_ref().map(|s| s.ovs.lookup_lost)),
            )
        ]
    };
    let rows = items.into_iter().map(|item| {
        let cells = [Cell::from(item.0), Cell::from(item.1)];
        Row::new(cells).height(1).bottom_margin(0)
    });
    let t = Table::new(rows)
        .header(header)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title("Open vSwitch statistics"),
        )
        //.highlight_style(selected_style)
        //.highlight_symbol(">> ")
        .widths(&[
            Constraint::Length(35),
            Constraint::Length(20),
        ]);
    f.render_stateful_widget(t, rects[0], &mut app.state);
}
