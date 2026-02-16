#![forbid(unsafe_code)]

mod canon;
mod cli;
mod hash;
mod kernel_sys;
mod ledger;
mod paths;
mod pinning;
mod plan;
mod protocols;
mod snapshot;
mod tools;
mod trace;

fn main() {
    let exit_code = match run() {
        Ok(code) => code,
        Err(reason) => {
            eprintln!("{reason}");
            30
        }
    };
    kernel_sys::exit(exit_code);
}

fn run() -> Result<i32, String> {
    let args = cli::parse_args()?;
    match args.command {
        cli::Command::Run { run_spec } => plan::execute_run(&run_spec),
    }
}
