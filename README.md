# ESPHome Nodes

Under development ESPHome config builder.

Uses Node-RED editor with a python runtime (though more apt to simply call it a python API replacement, and currently no runtime (will be ESPHome))

Currently very early in development, only looks at flow in first tab.

Contains a few hand-built nodes with minimal subsets of their complete configurations.

## Development

Check out this repository, `cd nodes`, run `npm install` and then run

```sh
python3 server.py /dir/of/yaml/and/flows/
```