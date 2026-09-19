import {
  useEffect,
  useState,
} from "react";


export default function ModelSelector({
  value,
  onChange,
}) {
  const [targets, setTargets] =
    useState([]);

  const [error, setError] =
    useState(null);


  useEffect(() => {
    let cancelled = false;


    async function loadTargets() {
      try {
        const response =
          await fetch(
            "/api/model-targets"
          );

        const payload =
          await response.json();

        if (!response.ok) {
          throw new Error(
            payload.error
            ?? `HTTP ${response.status}`
          );
        }

        if (cancelled) {
          return;
        }

        const available =
          payload.targets ?? [];

        setTargets(
          available
        );

        if (
          !value
          && available.length
        ) {
          onChange?.(
            available[0].id
          );
        }
      }
      catch (err) {
        if (!cancelled) {
          setError(
            String(err)
          );
        }
      }
    }


    loadTargets();


    return () => {
      cancelled = true;
    };
  }, []);


  return (
    <div className="model-selector">

      <span className="model-selector-label">
        DECOMPOSITION MODEL
      </span>

      {error ? (
        <span className="model-selector-error">
          Model registry unavailable
        </span>
      ) : (
        <select
          value={value ?? ""}
          onChange={(event) => {
            onChange?.(
              event.target.value
            );
          }}
        >
          {!targets.length && (
            <option value="">
              Loading...
            </option>
          )}

          {targets.map(
            (target) => (
              <option
                key={target.id}
                value={target.id}
              >
                {target.label}
              </option>
            )
          )}
        </select>
      )}

    </div>
  );
}
