-- Dépannage : à exécuter dans la console Postgres de Railway uniquement si le
-- redéploiement ne peut pas être fait tout de suite. La version 2.1.1 ajoute ces
-- colonnes d'elle-même au démarrage ; ce script ne fait que devancer la migration.
-- Il est sans effet si les colonnes existent déjà.

ALTER TABLE activites ADD COLUMN IF NOT EXISTS date_theorique DATE;
ALTER TABLE activites ADD COLUMN IF NOT EXISTS valide_le TIMESTAMP;
ALTER TABLE activites ADD COLUMN IF NOT EXISTS valide_par_id INTEGER;
ALTER TABLE activites ADD COLUMN IF NOT EXISTS origine_estimee BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE recurrences ADD COLUMN IF NOT EXISTS reporter BOOLEAN NOT NULL DEFAULT TRUE;

-- Les séances déjà générées par une règle récupèrent leur date théorique.
UPDATE activites SET date_theorique = date
WHERE recurrence_id IS NOT NULL AND date_theorique IS NULL;

-- Contrôle : les cinq colonnes doivent apparaître.
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE (table_name = 'activites'
       AND column_name IN ('date_theorique', 'valide_le', 'valide_par_id', 'origine_estimee'))
   OR (table_name = 'recurrences' AND column_name = 'reporter')
ORDER BY table_name, column_name;
