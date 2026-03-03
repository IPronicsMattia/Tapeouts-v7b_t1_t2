# IPronics Layout library for tapeouts
![logo](https://github.com/iPronics/IPRLAYOUT_Tower/blob/feature/clean_first_update/img/logo.png)

## Installation for development

1. Clone the IPRLAYOUT_* repos
2. Clone this repo and change to its root dir (Both this repostiory and IPRLAYOUT_* should share the same parent directory)
3. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
   
   Windows:
    ```
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```
   Linux:
   ```
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   Note: when using uv in the project, you may be prompted to update the uv version to match the configured one. This can be done with:
   ```
   uv self update <version>
   ```
4. "Sync" your local ".venv" environment (it is created if it does not exist).
   ```
   uv sync
   ```

## Working with `uv`

The usage of `uv` introduces some changes with respect to the more traditional usage of virtual environments.

`uv` has a very good and detailed [documentation](https://docs.astral.sh/uv). At the very least make sure to read the instructions for [working on projects](https://docs.astral.sh/uv/guides/projects/)

Here are some tips:

1. a _project virtual environment_ called `.venv` is automatically created in the root of the project **but you do not need to manually activate it or any other environment**. `uv` will internally activate `.venv` when needed but this should be transparent to you.
2. To run commands _within the project virtual environment_, you just use `uv run [--with <additional_module>] <command>`. For example, to run a specific test with pytest:
   ```
   uv run pytest tests/test_foo.py
   ```
   ... or to launch an ipython session on the project virtual environment (note that `ipython` is not installed in `.venv`, so we install it on-the-fly without contaminating the environment):
   ```
   uv run --with ipython ipython
   ```
3. **when working with an IDE** (e.g., VSCodium) **make sure that it is configured to use the `.venv` project virtual environment**.
4. `uv` provides a `uv pip` command that can be used as a replacement of `pip` and to enable working in the "old style" (explicit activation of the environment, etc.) **but it is strongly recommended to use the new "uv-native" way of working** instead.
5. `uv` uses a [`uv.lock` file](https://docs.astral.sh/uv/guides/projects/#uvlock) that stores the "pinned" dependencies for the project. This file is kept under version control and should not be edited manually.
6. if you want to add a new dependency to the project, [use `uv add <module>`](https://docs.astral.sh/uv/guides/projects/#managing-dependencies).
 
