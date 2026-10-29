"""Updater asset selection: Windows must get the zip, not rar/tar.gz."""

from __future__ import annotations

from src import net, updater


def test_zapret_prefers_zip_asset() -> None:
    meta = updater.COMPONENTS["zapret"]
    release = net.Release(
        repo="Flowseal/zapret-discord-youtube",
        tag="1.10.4",
        name="1.10.4",
        assets=[
            net.Asset("zapret-discord-youtube-1.10.4.rar", "https://example/rar"),
            net.Asset("zapret-discord-youtube-1.10.4.tar.gz", "https://example/tar"),
            net.Asset("zapret-discord-youtube-1.10.4.zip", "https://example/zip"),
        ],
    )
    asset = net.pick_asset(release, meta["keywords"], exclude=meta["exclude"])
    assert asset is not None
    assert asset.name.endswith(".zip")
