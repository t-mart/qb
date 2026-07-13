from pathlib import Path

from pydantic import BaseModel
import yaml


def both_yaml_suffix_spellings(path: Path) -> list[Path]:
    return [path.with_suffix(".yaml"), path.with_suffix(".yml")]


config_paths = [
    *both_yaml_suffix_spellings(Path.home() / ".config/qb/config.yaml"),
]


class ClientConfig(BaseModel):
    url: str
    username: str
    password: str


class Config(BaseModel):
    clients: dict[str, ClientConfig]

    @classmethod
    def load_from_file(cls) -> Config:
        for config_path in config_paths:
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as f:
                    yaml_config = yaml.safe_load(f)
                return cls(**yaml_config)
        raise FileNotFoundError("No configuration file found in expected locations.")


if __name__ == "__main__":
    config = Config.load_from_file()
    print(config)
