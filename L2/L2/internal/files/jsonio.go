package files

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"L2/internal/model"
)

func ReadJSON(path string) (model.PlayersWrapper, error) {
	var w model.PlayersWrapper
	b, err := os.ReadFile(path)
	if err != nil {
		return w, err
	}

	b = bytes.TrimPrefix(b, []byte{0xEF, 0xBB, 0xBF})
	if err := json.Unmarshal(b, &w); err != nil {
		return w, err
	}

	return w, nil
}

func WriteResults(path string, starting []model.VolleyballPlayer, results []model.VolleyballPlayer) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil && !errors.Is(err, os.ErrExist) {
		// ignore if already exists
	}

	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	out := bufio.NewWriter(f)
	defer out.Flush()

	fmt.Fprintln(out, "STARTING DATA")
	fmt.Fprintln(out, "Name                 |   Games |   Winning")
	fmt.Fprintln(out, strings.Repeat("-", 50))

	for _, p := range starting {
		fmt.Fprintf(out, "%-20s | %7d | %8.2f\n", p.Name, p.Games, p.Winning)
	}

	fmt.Fprintln(out)
	fmt.Fprintln(out, "RESULTS (filtered)")
	fmt.Fprintln(out, "Name                 |   Games |   Winning")
	fmt.Fprintln(out, strings.Repeat("-", 50))

	for i, p := range results {
		fmt.Fprintf(out, "%d %-20s | %7d | %8.2f\n", i, p.Name, p.Games, p.Winning)
	}

	return nil
}
