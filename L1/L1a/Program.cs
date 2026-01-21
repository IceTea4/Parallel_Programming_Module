namespace L1a
{
    class Program
    {
        static void Main(string[] args)
        {
            PlayersWrapper json = InOut.Read("../../../IFF3_1_JakutonisA_L1_dat_1.json");

            var players = json.Player;
            int size = players.Count / 4;

            var dataMonitor = new DataMonitor(size);
            var resultMonitor = new ResultMonitor(players.Count);
            var threads = new List<Thread>();

            for (int i = 0; i < size; i++)
            {
                var t = new Thread(() =>
                {
                    VolleyballPlayer player;

                    while ((player = dataMonitor.RemoveItem()) != null)
                    {
                        //Console.WriteLine($"Paėmiau {player.Name}, monitoriuje liko: {dataMonitor.GetCount()}");

                        if (Function(player))
                        {
                            if (Filter(player))
                            {
                                resultMonitor.AddItemSorted(player);
                            }
                        }
                    }
                });

                t.Start();
                threads.Add(t);
            }

            foreach (var p in players)
            {
                dataMonitor.AddItem(p);
                //Console.WriteLine($"Įdėjau {p.Name}, monitoriuje dabar: {dataMonitor.GetCount()}");
            }

            dataMonitor.Complete();

            foreach (var t in threads)
            {
                t.Join();
            }

            var results = resultMonitor.GetItems();

            InOut.Write("../../../IFF3_JakutonisA_L1_rez.txt", players, results);
        }

        static bool Function(VolleyballPlayer player)
        {
            double score = player.Winning * player.Games;
            int x = 0;

            while (x < 1000000000)
            {
                x++;
            }

            return score >= 400;
        }

        static bool Filter(VolleyballPlayer player)
        {
            if (player.Winning >= 50)
            {
                return true;
            }

            return false;
        }
    }
}
