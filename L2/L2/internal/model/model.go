package model

type VolleyballPlayer struct {
	Name    string  `json:"name"`
	Games   int     `json:"games"`
	Winning float64 `json:"winning"`
}

type PlayersWrapper struct {
	Player []VolleyballPlayer `json:"player"`
}
